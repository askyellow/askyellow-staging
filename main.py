from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from dotenv import load_dotenv
from openai import OpenAI
from datetime import datetime
from chat_engine.routes import router as chat_router
from fastapi.responses import FileResponse
import os
import uvicorn
import requests
import unicodedata
import re
import secrets


# DB
import psycopg2
import psycopg2.extras


# =============================================================
# 0. PAD & KNOWLEDGE ENGINE IMPORTS
# =============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

from yellowmind.knowledge_engine import load_knowledge, match_question
from yellowmind.identity_origin import try_identity_origin_answer


# =============================================================
# 1. ENVIRONMENT & OPENAI CLIENT
# =============================================================

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is missing")

client = OpenAI(api_key=OPENAI_API_KEY)

YELLOWMIND_MODEL = os.getenv("YELLOWMIND_MODEL")
if not YELLOWMIND_MODEL:
    print("⚠️ Geen YELLOWMIND_MODEL env gevonden → fallback naar o3-mini")
    YELLOWMIND_MODEL = "o3-mini"

VALID_MODELS = [
    "o3-mini",
    "o1-mini",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4o-mini",
]


APP_ENV = os.getenv("APP_ENV", "live")
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")

print(f"🌍 YellowMind environment: {APP_ENV} (version {APP_VERSION})")

if YELLOWMIND_MODEL not in VALID_MODELS:
    print(f"⚠️ Onbekend model '{YELLOWMIND_MODEL}' → fallback naar o3-mini")
    YELLOWMIND_MODEL = "o3-mini"

print(f"🧠 Yellowmind gebruikt model: {YELLOWMIND_MODEL}")

SQL_SEARCH_URL = os.getenv(
    "SQL_SEARCH_URL",
    "https://www.askyellow.nl/search_knowledge.php"
)

# =============================================================
# 2. FASTAPI APP & CORS
# =============================================================

app = FastAPI(title="YellowMind API")

app.include_router(chat_router, prefix="/chat")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/chat")
def serve_chat_page():
    base = os.path.dirname(os.path.abspath(__file__))
    return FileResponse(os.path.join(base, "static/chat/chat.html"))


@app.get("/health")
def health():
    """Eenvoudige healthcheck met DB-status en environment-info."""
    db_ok = True
    try:
        # get_db wordt later in dit bestand gedefinieerd,
        # maar hier pas bij aanroep gebruikt → geen NameError meer.
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT 1")
        cur.close()
        db.close()
    except Exception:
        db_ok = False

    return {
        "status": "ok",
        "env": APP_ENV,
        "version": APP_VERSION,
        "db_ok": db_ok,
    }

# =============================================================
# POSTGRES DB FOR USERS / CONVERSATIONS / MESSAGES
# =============================================================

# DATABASE_URL komt uit de Render-omgeving
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is niet ingesteld (env var DATABASE_URL).")

def get_db_conn():
    """Open een nieuwe PostgreSQL-verbinding met dict-rows."""
    conn = psycopg2.connect(
        DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor
    )
    return conn

def get_db():
    """FastAPI dependency die de verbinding automatisch weer sluit."""
    conn = get_db_conn()
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """Maak basis-tabellen aan als ze nog niet bestaan."""
    conn = get_db_conn()
    cur = conn.cursor()

    # Users: 1 rij per (anon/persoonlijke) sessie
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            session_id TEXT UNIQUE NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )

    # Conversations: 1 of meer gesprekken per user
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_message_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            title TEXT
        );
        """
    )

    # Messages: alle losse berichten
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )

    conn.commit()
    conn.close()

@app.on_event("startup")
def on_startup():
    # Zorg dat de tabellen bestaan bij het starten van de app
    init_db()


def get_or_create_user(conn, session_id: str) -> int:
    """Zoek user op session_id, maak anders een nieuwe aan."""
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE session_id = %s", (session_id,))
    row = cur.fetchone()
    if row:
        return row["id"]

    cur.execute(
        "INSERT INTO users (session_id) VALUES (%s) RETURNING id",
        (session_id,),
    )
    new_id = cur.fetchone()["id"]
    return new_id


def get_or_create_conversation(conn, user_id: int) -> int:
    """
    Zorgt ervoor dat een user maar 1 gesprek heeft.
    Bestaat er al een conversatie voor deze user? Gebruik die.
    Zo niet: maak er één aan.
    """
    cur = conn.cursor()

    # 1) bestaat er al een conversatie voor deze user?
    cur.execute(
        """
        SELECT id
        FROM conversations
        WHERE user_id = %s
        ORDER BY id ASC
        LIMIT 1
        """,
        (user_id,),
    )
    row = cur.fetchone()
    if row:
        conv_id = row["id"]
        # optioneel: last_message_at updaten bij elke interactie
        cur.execute(
            "UPDATE conversations SET last_message_at = NOW() WHERE id = %s",
            (conv_id,),
        )
        return conv_id

    # 2) geen conversatie → maak er één aan
    cur.execute(
        """
        INSERT INTO conversations (user_id)
        VALUES (%s)
        RETURNING id
        """,
        (user_id,),
    )
    conv_id = cur.fetchone()["id"]
    return conv_id


def save_message(conn, conversation_id: int, role: str, content: str):
    cur = conn.cursor()
    # message opslaan
    cur.execute(
        """
        INSERT INTO messages (conversation_id, role, content)
        VALUES (%s, %s, %s)
        """,
        (conversation_id, role, content),
    )
    # last_message_at bijwerken
    cur.execute(
        """
        UPDATE conversations
        SET last_message_at = NOW()
        WHERE id = %s
        """,
        (conversation_id,),
    )





# =============================================================
# 3. HELPERS: LOAD FILES & PROMPT
# =============================================================

def load_file(path: str) -> str:
    full_path = os.path.join(BASE_DIR, path)
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            return "\n" + f.read().strip() + "\n"
    except FileNotFoundError:
        print(f"⚠️ Yellowmind config file niet gevonden: {full_path}")
        return ""

def build_system_prompt() -> str:
    base = "yellowmind/"
    system_prompt = ""

    # SYSTEM CORE
    system_prompt += load_file(base + "system/yellowmind_master_prompt_v2.txt")
    system_prompt += load_file(base + "core/core_identity.txt")
    system_prompt += load_file(base + "core/mission.txt")
    system_prompt += load_file(base + "core/values.txt")
    system_prompt += load_file(base + "core/introduction_rules.txt")
    system_prompt += load_file(base + "core/communication_baseline.txt")

    # PARENTS
    system_prompt += load_file(base + "parents/parent_profile_brigitte.txt")
    system_prompt += load_file(base + "parents/parent_profile_dennis.txt")
    system_prompt += load_file(base + "parents/parent_profile_yello.txt")
    system_prompt += load_file(base + "parents/parent_mix_logic.txt")

    # BEHAVIOUR
    system_prompt += load_file(base + "behaviour/behaviour_rules.txt")
    system_prompt += load_file(base + "behaviour/boundaries_safety.txt")
    system_prompt += load_file(base + "behaviour/escalation_rules.txt")
    system_prompt += load_file(base + "behaviour/uncertainty_handling.txt")
    system_prompt += load_file(base + "behaviour/user_types.txt")

    # KNOWLEDGE
    system_prompt += load_file(base + "knowledge/knowledge_sources.txt")
    system_prompt += load_file(base + "knowledge/askyellow_site_rules.txt")
    system_prompt += load_file(base + "knowledge/product_rules.txt")
    system_prompt += load_file(base + "knowledge/no_hallucination_rules.txt")
    system_prompt += load_file(base + "knowledge/limitations.txt")

    # TONE
    system_prompt += load_file(base + "tone/tone_of_voice.txt")
    system_prompt += load_file(base + "tone/branding_mode.txt")
    system_prompt += load_file(base + "tone/empathy_mode.txt")
    system_prompt += load_file(base + "tone/tech_mode.txt")
    system_prompt += load_file(base + "tone/storytelling_mode.txt")
    system_prompt += load_file(base + "tone/concise_mode.txt")

    return system_prompt.strip()

SYSTEM_PROMPT = build_system_prompt()
KNOWLEDGE_ENTRIES = load_knowledge()

# =============================================================
# 4. SQL KNOWLEDGE LAYER
# =============================================================

def normalize(text: str) -> str:
    text = text.lower().strip()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text

def jaccard_score(a: str, b: str) -> float:
    wa = set(normalize(a).split())
    wb = set(normalize(b).split())
    if not wa or not wb:
        return 0.0
    inter = wa.intersection(wb)
    union = wa.union(wb)
    return len(inter) / len(union)

def compute_match_score(user_q: str, cand_q: str) -> int:
    j = jaccard_score(user_q, cand_q)
    contains = 1.0 if normalize(cand_q) in normalize(user_q) else 0.0
    score = int((0.7 * j + 0.3 * contains) * 100)
    return max(0, min(score, 100))

def search_sql_knowledge(question: str):
    try:
        resp = requests.post(SQL_SEARCH_URL, data={"q": question}, timeout=3)
        if resp.status_code != 200:
            print("⚠️ SQL STATUS:", resp.status_code)
            return None
        data = resp.json()
    except Exception as e:
        print("⚠️ SQL ERROR:", e)
        return None

    best = None
    best_score = 0

    for row in data:
        score = compute_match_score(question, row.get("question",""))
        if score > best_score:
            best_score = score
            best = {
                "id": row.get("id"),
                "question": row.get("question",""),
                "answer": row.get("answer",""),
                "score": score
            }

    if best:
        print(f"🧠 SQL BEST MATCH SCORE={best_score}")
    return best


# =============================================================
# 5. MODE DETECTION
# =============================================================

def detect_hints(question: str):
    q = question.lower()
    mode = "auto"
    context = "general"
    user = None

    if any(x in q for x in ["api", "bug", "foutmelding", "script", "dns"]):
        mode = "tech"
    if any(x in q for x in ["askyellow", "yellowmind", "logo", "branding"]):
        mode = "branding"
        context = "askyellow"
    if any(x in q for x in ["ik voel me", "overprikkeld", "huil"]):
        mode = "empathy"
        user = "emotioneel"

    return {
        "mode_hint": mode,
        "context_type": context,
        "user_type_hint": user
    }


# =============================================================
# 6. OPENAI CALL — FIXED FOR o3 RESPONSE FORMAT (SAFE)
# =============================================================

def call_yellowmind_llm(question, language, kb_answer, sql_match, hints):
    messages = []

    messages.append({"role": "system", "content": SYSTEM_PROMPT})

    knowledge_blocks = []

    if kb_answer:
        knowledge_blocks.append("STATIC_KB:\n" + kb_answer)

    if sql_match:
        knowledge_blocks.append(
            "SQL_KB:\n"
            f"Vraag: {sql_match['question']}\n"
            f"Antwoord: {sql_match['answer']}\n"
            f"Score: {sql_match['score']}"
        )

    if knowledge_blocks:
        messages.append({"role": "system", "content": "[ASKYELLOW_KNOWLEDGE]\n" + "\n\n".join(knowledge_blocks)})

    if hints:
        hint_text = "\n".join([f"- {k}: {v}" for k,v in hints.items() if v])
        messages.append({"role": "system", "content": "[BACKEND_HINTS]\n" + hint_text})

    messages.append({"role": "user", "content": question})

    selected_model = YELLOWMIND_MODEL
    print(f"🤖 Model geselecteerd: {selected_model}")

    # OpenAI Responses API
    llm_response = client.responses.create(
        model=selected_model,
        input=messages
    )

    # =============================================================
    # SAFE ANSWER EXTRACTOR
    # =============================================================

    answer_text = None

    try:
        # 1. Zoek expliciet naar assistant message blocks
        for block in llm_response.output:
            if hasattr(block, "type") and block.type == "message":
                if getattr(block, "role", None) == "assistant":
                    try:
                        answer_text = block.content[0].text
                        break
                    except:
                        pass

        # 2. Fallback: pak eerste block met content
        if not answer_text:
            for block in llm_response.output:
                if hasattr(block, "content") and block.content:
                    try:
                        answer_text = block.content[0].text
                        break
                    except:
                        pass

        # 3. Als er nog steeds geen tekst is:
        if not answer_text:
            answer_text = "⚠️ Geen leesbare assistant-output ontvangen."

    except Exception as e:
        print("❌ EXTRACT ERROR SAFE:", e)
        answer_text = "⚠️ Ik kon het modelantwoord niet verwerken."

    return answer_text, llm_response.output

# =============================================================
# X. PERFORMANCE STATUS CHECK
# =============================================================

import time

def detect_cold_start(sql_ms, kb_ms, ai_ms, total_ms):
    if ai_ms > 6000:
        return "🔥 COLD START — model wakker gemaakt"
    if sql_ms > 800:
        return "❄️ SLOW SQL"
    if kb_ms > 200:
        return "⚠️ KB slow"
    if total_ms > 5000:
        return "⏱️ Slow total"
    return "✓ warm"


@app.post("/ask")
async def ask_ai(request: Request):
    data = await request.json()
    question = (data.get("question") or "").strip()
    language = (data.get("language") or "nl").lower()

    # session_id
    session_id = (
        data.get("session_id")
        or data.get("sessionId")
        or data.get("session")
        or data.get("sid")
        or ""
    )
    session_id = str(session_id).strip()
    if not session_id:
        session_id = "anon-" + secrets.token_hex(8)

    # FINAL ANSWER SAFETY NET
    final_answer = None
    raw_output = []

    if not question:
        final_answer = "Geen vraag ontvangen."
        return JSONResponse(
            status_code=400,
            content={"error": final_answer},
        )

    # =============================================================
    # 1. QUICK IDENTITY
    # =============================================================
    identity_answer = try_identity_origin_answer(question, language)
    if identity_answer:
        final_answer = identity_answer
        _log_message_safe(session_id, question, final_answer)
        return {
            "answer": final_answer,
            "output": [],
            "source": "identity_origin",
            "kb_used": False,
            "sql_used": False,
            "sql_score": None,
            "hints": {}
        }

    # =============================================================
    # 2. SQL KNOWLEDGE
    # =============================================================
    sql_match = search_sql_knowledge(question)
    if sql_match and sql_match["score"] >= 60:
        final_answer = sql_match["answer"]
        _log_message_safe(session_id, question, final_answer)
        return {
            "answer": final_answer,
            "output": [],
            "source": "sql",
            "kb_used": False,
            "sql_used": True,
            "sql_score": sql_match["score"],
            "hints": {}
        }

    # =============================================================
    # 3. JSON KNOWLEDGE ENGINE
    # =============================================================
    try:
        kb_answer = match_question(question, KNOWLEDGE_ENTRIES)
    except:
        kb_answer = None

    hints = detect_hints(question)

    # =============================================================
    # 4. LLM FALLBACK
    # =============================================================
    start_ai = time.time()
    final_answer, raw_output = call_yellowmind_llm(
        question, language, kb_answer, sql_match, hints
    )

    # FINAL ANSWER SAFETY
    if not final_answer:
        final_answer = "⚠️ Geen geldig antwoord beschikbaar."

    # =============================================================
    # PERFORMANCE LOGGING
    # =============================================================
    sql_ms = 0
    kb_ms = 0
    ai_ms = int((time.time() - start_ai) * 1000)
    total_ms = ai_ms

    try:
        for block in raw_output:
            if hasattr(block, "type") and block.type == "response.stats":
                sql_ms = getattr(block, "sql_ms", 0)
                kb_ms = getattr(block, "kb_ms", 0)
                total_ms = getattr(block, "total_ms", ai_ms)
    except:
        pass

    status = detect_cold_start(sql_ms, kb_ms, ai_ms, total_ms)

    print(f"[STATUS] {status}")
    print(f"[SQL] {sql_ms} ms")
    print(f"[KB] {kb_ms} ms")
    print(f"[AI] {ai_ms} ms")
    print(f"[TOTAL] {total_ms} ms")

    # =============================================================
    # DATABASE LOGGING (SAFE)
    # =============================================================
    _log_message_safe(session_id, question, final_answer)

    return {
        "answer": final_answer,
        "output": raw_output,
        "source": "yellowmind_llm",
        "kb_used": bool(kb_answer),
        "sql_used": bool(sql_match),
        "sql_score": sql_match["score"] if sql_match else None,
        "hints": hints
    }


def _log_message_safe(session_id, question, final_answer):
    """Veilig loggen zonder dat fouten de assistent breken."""
    try:
        conn = get_db_conn()
        user_id = get_or_create_user(conn, session_id)
        conv_id = get_or_create_conversation(conn, user_id)

        save_message(conn, conv_id, "user", question)
        save_message(conn, conv_id, "assistant", final_answer)

        conn.commit()
        conn.close()
    except Exception as e:
        print("❌ DB logging error:", e)


# =============================================================
# 8. LOCAL DEV
# =============================================================


# =============================================================
# 9. ADMIN ENDPOINTS (PostgreSQL)
# =============================================================

ADMIN_KEY = "Yellow_Master_Mind!"

def admin_auth(key: str):
    if key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")


@app.get("/admin/messages")
def admin_messages(key: str, db=Depends(get_db)):
    """Laatste 50 berichten (incl. sessie & conversation info)."""
    admin_auth(key)
    cur = db.cursor()
    cur.execute(
        """
        SELECT
            m.id,
            m.created_at,
            m.role,
            m.content,
            m.conversation_id,
            c.user_id,
            u.session_id
        FROM messages m
        JOIN conversations c ON m.conversation_id = c.id
        JOIN users u ON c.user_id = u.id
        ORDER BY m.created_at DESC, m.id DESC
        LIMIT 50
        """
    )
    rows = cur.fetchall()
    return rows


@app.get("/admin/conversations")
def admin_conversations(key: str, db=Depends(get_db)):
    """Overzicht van alle conversaties."""
    admin_auth(key)
    cur = db.cursor()
    cur.execute(
        """
        SELECT
            c.id,
            c.started_at,
            c.last_message_at,
            u.session_id
        FROM conversations c
        JOIN users u ON c.user_id = u.id
        ORDER BY c.last_message_at DESC, c.id DESC
        """
    )
    return cur.fetchall()


@app.get("/admin/conversation/{conv_id}")
def admin_conversation(conv_id: int, key: str, db=Depends(get_db)):
    """Alle berichten van één conversatie."""
    admin_auth(key)
    cur = db.cursor()
    cur.execute(
        """
        SELECT
            m.id,
            m.created_at,
            m.role,
            m.content
        FROM messages m
        WHERE m.conversation_id = %s
        ORDER BY m.created_at ASC, m.id ASC
        """,
        (conv_id,),
    )
    return cur.fetchall()


@app.get("/admin/stats")
def admin_stats(key: str, db=Depends(get_db)):
    """Simpele stats voor dashboard."""
    admin_auth(key)
    cur = db.cursor()

    cur.execute("SELECT COUNT(*) AS cnt FROM users")
    users = cur.fetchone()["cnt"]

    cur.execute("SELECT COUNT(*) AS cnt FROM conversations")
    conversations = cur.fetchone()["cnt"]

    cur.execute("SELECT COUNT(*) AS cnt FROM messages")
    messages = cur.fetchone()["cnt"]

    cur.execute(
        """
        SELECT
            m.id,
            m.created_at,
            m.role,
            m.content,
            m.conversation_id
        FROM messages m
        ORDER BY m.created_at DESC, m.id DESC
        LIMIT 1
        """
    )
    last_msg = cur.fetchone()

    return {
        "users": users,
        "conversations": conversations,
        "messages": messages,
        "last_message": last_msg,
    }
# =============================================================
#  AUTH SYSTEM (REGISTER, LOGIN, ME, LOGOUT)
# =============================================================

# =============================================================
#  AUTH SYSTEM (REGISTER, LOGIN, ME, LOGOUT)
#  Compatible with existing get_db_conn() usage
# =============================================================

from pydantic import BaseModel
import bcrypt
import secrets
import datetime


# -----------------------------
#  Pydantic Models
# -----------------------------
class RegisterInput(BaseModel):
    email: str
    password: str
    first_name: str
    last_name: str

class LoginInput(BaseModel):
    email: str
    password: str


# -----------------------------
#  Helper Functions
# -----------------------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def create_user_session(conn, user_id: int) -> str:
    session_id = "auth-" + secrets.token_hex(32)
    expires = datetime.datetime.utcnow() + datetime.timedelta(days=14)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO user_sessions (session_id, user_id, expires_at) VALUES (%s, %s, %s)",
        (session_id, user_id, expires)
    )
    return session_id

def get_user_from_session(conn, session_id: str):
    cur = conn.cursor()
    cur.execute("""
        SELECT u.id, u.email, u.created_at, u.first_name, u.last_name
        FROM users u
        JOIN user_sessions s ON s.user_id = u.id
        WHERE s.session_id = %s
        AND s.expires_at > NOW()
    """, (session_id,))
    return cur.fetchone()


# =============================================================
#  LOGIN
# =============================================================
@app.post("/auth/login")
def login(data: LoginInput):
    conn = get_db_conn()
    cur = conn.cursor()

    email = data.email.strip().lower()
    pw = data.password.strip()

    # Haal ook first_name en last_name op
    cur.execute("""
        SELECT id, password_hash, first_name, last_name
        FROM users
        WHERE email = %s
    """, (email,))
    row = cur.fetchone()

    if not row or not verify_password(pw, row["password_hash"]):
        conn.close()
        raise HTTPException(status_code=400, detail="Ongeldige login.")

    user_id = row["id"]
    first = row["first_name"]
    last = row["last_name"]

    # Update last login
    cur.execute("UPDATE users SET last_login = NOW() WHERE id = %s", (user_id,))

    # Maak nieuwe sessie
    session_id = create_user_session(conn, user_id)

    conn.commit()
    conn.close()

    return {
        "success": True,
        "session": session_id,
        "user_id": user_id,
        "first_name": first,
        "last_name": last
    }
