from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from dotenv import load_dotenv
from openai import OpenAI
import os
import uvicorn
import requests
import unicodedata
import re
import time
import sqlite3
import bcrypt
import jwt
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import uuid4

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

if YELLOWMIND_MODEL not in VALID_MODELS:
    print(f"⚠️ Onbekend model '{YELLOWMIND_MODEL}' → fallback naar o3-mini")
    YELLOWMIND_MODEL = "o3-mini"

print(f"🧠 Yellowmind gebruikt model: {YELLOWMIND_MODEL}")

SQL_SEARCH_URL = os.getenv(
    "SQL_SEARCH_URL",
    "https://www.askyellow.nl/search_knowledge.php"
)

# JWT / DB config
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-env")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "43200"))  # default 30 dagen
DB_PATH = os.getenv("DB_PATH", os.path.join(BASE_DIR, "yellowmind.db"))
SESSION_COOKIE_NAME = "askyellow_session"


# =============================================================
# 2. FASTAPI APP & CORS
# =============================================================

app = FastAPI(title="YellowMind API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # evt. later strakker maken als je cookies gaat gebruiken
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
# 4. SQLITE DB + AUTH (USERS / CONVERSATIONS / MESSAGES)
# =============================================================

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # users
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )

    # conversations
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            user_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """
    )

    # messages
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            sender TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        );
        """
    )

    conn.commit()
    conn.close()


@app.on_event("startup")
def on_startup():
    init_db()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=JWT_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Ongeldige of verlopen sessie")


def get_current_user(request: Request, db=Depends(get_db)) -> Optional[sqlite3.Row]:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None

    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Ongeldige token payload")

    cur = db.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Gebruiker niet gevonden")

    return row


@app.post("/auth/register")
def register_user(data: dict, response: Response, db=Depends(get_db)):
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email en wachtwoord zijn verplicht")

    cur = db.cursor()
    cur.execute("SELECT id FROM users WHERE email = ?", (email,))
    if cur.fetchone():
        raise HTTPException(status_code=400, detail="Email is al geregistreerd")

    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    now = datetime.utcnow().isoformat()
    cur.execute(
        "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
        (email, password_hash, now),
    )
    db.commit()

    user_id = cur.lastrowid
    token = create_access_token({"sub": str(user_id)})
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=JWT_EXPIRE_MINUTES * 60,
    )

    return {"id": user_id, "email": email}


@app.post("/auth/login")
def login_user(data: dict, response: Response, db=Depends(get_db)):
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email en wachtwoord zijn verplicht")

    cur = db.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (email,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="Onjuiste inloggegevens")

    stored_hash = row["password_hash"]
    if not bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8")):
        raise HTTPException(status_code=400, detail="Onjuiste inloggegevens")

    token = create_access_token({"sub": str(row["id"])})
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=JWT_EXPIRE_MINUTES * 60,
    )

    return {"id": row["id"], "email": row["email"]}


@app.post("/auth/logout")
def logout_user(response: Response):
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"message": "Uitgelogd"}


@app.get("/auth/me")
def get_me(current_user=Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=401, detail="Niet ingelogd")
    return {"id": current_user["id"], "email": current_user["email"]}


# Conversation helpers

def ensure_conversation(db, conversation_id: str, user: Optional[sqlite3.Row]) -> str:
    """
    Zorgt dat een conversation record bestaat voor dit id.
    Als hij niet bestaat → maak hem aan. Koppelt eventueel user_id.
    """
    cur = db.cursor()
    cur.execute("SELECT id, user_id FROM conversations WHERE id = ?", (conversation_id,))
    row = cur.fetchone()
    now = datetime.utcnow().isoformat()

    if row:
        # eventueel achteraf user_id invullen als het nog None is
        if user and row["user_id"] is None:
            cur.execute(
                "UPDATE conversations SET user_id = ? WHERE id = ?",
                (user["id"], conversation_id),
            )
            db.commit()
        return conversation_id

    user_id = user["id"] if user else None
    cur.execute(
        "INSERT INTO conversations (id, user_id, created_at) VALUES (?, ?, ?)",
        (conversation_id, user_id, now),
    )
    db.commit()
    return conversation_id


def get_or_create_conversation_for_user(db, user: sqlite3.Row) -> str:
    """
    1 vaste conversation per ingelogde user.
    """
    cur = db.cursor()
    cur.execute("SELECT id FROM conversations WHERE user_id = ? ORDER BY created_at ASC LIMIT 1", (user["id"],))
    row = cur.fetchone()
    if row:
        return row["id"]

    conv_id = str(uuid4())
    now = datetime.utcnow().isoformat()
    cur.execute(
        "INSERT INTO conversations (id, user_id, created_at) VALUES (?, ?, ?)",
        (conv_id, user["id"], now),
    )
    db.commit()
    return conv_id


def create_anonymous_conversation(db) -> str:
    conv_id = str(uuid4())
    now = datetime.utcnow().isoformat()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO conversations (id, user_id, created_at) VALUES (?, ?, ?)",
        (conv_id, None, now),
    )
    db.commit()
    return conv_id


def get_messages_for_conversation(db, conversation_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    cur = db.cursor()
    cur.execute(
        """
        SELECT sender, text FROM messages
        WHERE conversation_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (conversation_id, limit),
    )
    rows = cur.fetchall()
    rows = list(rows)[::-1]  # oudste eerst
    messages: List[Dict[str, str]] = []
    for r in rows:
        sender = r["sender"]
        if sender == "assistant":
            role = "assistant"
        elif sender == "user":
            role = "user"
        else:
            role = "system"
        messages.append({"role": role, "content": r["text"]})
    return messages


def save_message(db, conversation_id: str, sender: str, text: str):
    now = datetime.utcnow().isoformat()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO messages (conversation_id, sender, text, created_at) VALUES (?, ?, ?, ?)",
        (conversation_id, sender, text, now),
    )
    db.commit()


@app.post("/api/start_conversation")
def start_conversation(
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Geeft een conversation_id terug.
    - Als user ingelogd: 1 vaste conversation per user.
    - Als user niet ingelogd: maakt een anonieme conversation aan.
    """
    if current_user:
        conv_id = get_or_create_conversation_for_user(db, current_user)
    else:
        conv_id = create_anonymous_conversation(db)
    return {"conversation_id": conv_id}


# =============================================================
# 5. SQL KNOWLEDGE LAYER
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
# 6. MODE DETECTION
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
# 7. OPENAI CALL — MET GESPREKSGESCHIEDENIS
# =============================================================

def call_yellowmind_llm(question, language, kb_answer, sql_match, hints, history_messages: Optional[List[Dict[str, str]]] = None):
    messages: List[Dict[str, str]] = []

    # Hoofd-systeemprompt
    messages.append({"role": "system", "content": SYSTEM_PROMPT})

    # Knowledge-blocks (zoals je had)
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
        if hint_text:
            messages.append({"role": "system", "content": "[BACKEND_HINTS]\n" + hint_text})

    # Gespreksgeschiedenis (user/assistant)
    if history_messages:
        messages.extend(history_messages)

    # Huidige vraag als laatste user-message
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
                    except Exception:
                        pass

        # 2. Fallback: pak eerste block met content
        if not answer_text:
            for block in llm_response.output:
                if hasattr(block, "content") and block.content:
                    try:
                        answer_text = block.content[0].text
                        break
                    except Exception:
                        pass

        # 3. Als er nog steeds geen tekst is:
        if not answer_text:
            answer_text = "⚠️ Geen leesbare assistant-output ontvangen."

    except Exception as e:
        print("❌ EXTRACT ERROR SAFE:", e)
        answer_text = "⚠️ Ik kon het modelantwoord niet verwerken."

    return answer_text, llm_response.output


# =============================================================
# 8. PERFORMANCE STATUS CHECK
# =============================================================

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


# =============================================================
# 9. ENDPOINTS (HEALTH + ASK MET MEMORY)
# =============================================================

@app.get("/")
async def root():
    return {"status": "ok", "message": "Yellowmind backend draait 🚀"}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/ping")
async def ping():
    return {
        "alive": True,
        "timestamp": time.time(),
        "status": "YellowMind awake"
    }

@app.head("/")
async def head_root():
    return Response(status_code=200)


@app.post("/ask")
async def ask_ai(
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Hoofd YellowMind endpoint.
    - Houdt je bestaande behaviour / KB / SQL logica intact.
    - Voegt conversation-memory toe op basis van conversation_id of ingelogde user.
    """
    data = await request.json()
    question = (data.get("question") or "").strip()
    language = (data.get("language") or "nl").lower()
    incoming_conv_id = (data.get("conversation_id") or "").strip()

    if not question:
        return JSONResponse(
            status_code=400,
            content={"error": "Geen vraag ontvangen."},
        )

    # 1) Conversation bepalen
    conversation_id: Optional[str] = None

    if incoming_conv_id:
        conversation_id = ensure_conversation(db, incoming_conv_id, current_user)
    elif current_user:
        conversation_id = get_or_create_conversation_for_user(db, current_user)
    else:
        # anonieme conversation
        conversation_id = create_anonymous_conversation(db)

    # 2) Geschiedenis ophalen (voor de AI)
    history_messages: List[Dict[str, str]] = []
    if conversation_id:
        history_messages = get_messages_for_conversation(db, conversation_id, limit=20)

    # 3) User-bericht opslaan in DB (als we een conversation hebben)
    if conversation_id:
        save_message(db, conversation_id, "user", question)

    # 4) QUICK IDENTITY
    identity_answer = try_identity_origin_answer(question, language)
    if identity_answer:
        if conversation_id:
            save_message(db, conversation_id, "assistant", identity_answer)

        return {
            "answer": identity_answer,
            "output": [],
            "source": "identity_origin",
            "kb_used": False,
            "sql_used": False,
            "sql_score": None,
            "hints": {},
            "conversation_id": conversation_id,
        }

    # 5) SQL KNOWLEDGE DIRECT HIT
    sql_match = search_sql_knowledge(question)
    if sql_match and sql_match["score"] >= 60:
        sql_answer = sql_match["answer"]
        if conversation_id:
            save_message(db, conversation_id, "assistant", sql_answer)

        return {
            "answer": sql_answer,
            "output": [],
            "source": "sql",
            "kb_used": False,
            "sql_used": True,
            "sql_score": sql_match["score"],
            "hints": {},
            "conversation_id": conversation_id,
        }

    # 6) JSON KNOWLEDGE ENGINE
    try:
        kb_answer = match_question(question, KNOWLEDGE_ENTRIES)
    except Exception:
        kb_answer = None

    # 7) Hints
    hints = detect_hints(question)

    # 8) LLM CALL MET HISTORY
    start_ai = time.time()
    final_answer, raw_output = call_yellowmind_llm(
        question=question,
        language=language,
        kb_answer=kb_answer,
        sql_match=sql_match,
        hints=hints,
        history_messages=history_messages,
    )
    ai_ms = int((time.time() - start_ai) * 1000)

    # 9) AI-antwoord opslaan
    if conversation_id:
        save_message(db, conversation_id, "assistant", final_answer)

    # 10) PERFORMANCE LOGGING (voor zover beschikbaar uit raw_output)
    sql_ms = 0
    kb_ms = 0
    total_ms = 0

    try:
        for block in raw_output:
            if hasattr(block, "type") and block.type == "response.stats":
                sql_ms = getattr(block, "sql_ms", 0)
                kb_ms = getattr(block, "kb_ms", 0)
                total_ms = getattr(block, "total_ms", 0)
    except Exception:
        pass

    status_msg = detect_cold_start(sql_ms, kb_ms, ai_ms, total_ms)

    print(f"[STATUS] {status_msg}")
    print(f"[SQL] {sql_ms} ms")
    print(f"[KB] {kb_ms} ms")
    print(f"[AI] {ai_ms} ms")
    print(f"[TOTAL] {total_ms} ms")

    return {
        "answer": final_answer,
        "output": raw_output,
        "source": "yellowmind_llm",
        "kb_used": bool(kb_answer),
        "sql_used": bool(sql_match),
        "sql_score": sql_match["score"] if sql_match else None,
        "hints": hints,
        "conversation_id": conversation_id,
    }


# =============================================================
# 10. LOCAL DEV
# =============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
