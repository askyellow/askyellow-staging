from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from dotenv import load_dotenv
from openai import OpenAI
from chat_engine.routes import router as chat_router
from fastapi.responses import FileResponse
import os
import uvicorn
import requests
import unicodedata
import re
import secrets

from datetime import datetime, timedelta
import uuid

# DB
import psycopg2
import psycopg2.extras
from psycopg2.extras import RealDictCursor
# chat
from chat_engine.db import get_conn
from chat_engine.utils import get_logical_date

# =============================================================
# SHOPIFY FUNCTIONS
# =============================================================

SHOPIFY_API_VERSION = "2025-10"

def shopify_get_products():
    url = f"https://{os.getenv('SHOPIFY_STORE_URL')}/admin/api/{SHOPIFY_API_VERSION}/products.json?limit=20"
    headers = {
        "X-Shopify-Access-Token": os.getenv("SHOPIFY_ACCESS_TOKEN")
    }
    response = requests.get(url, headers=headers)
    return response.json()
def shopify_search_products(query: str):
    url = f"https://{os.getenv('SHOPIFY_STORE_URL')}/admin/api/{SHOPIFY_API_VERSION}/products.json"
    headers = {"X-Shopify-Access-Token": os.getenv("SHOPIFY_ACCESS_TOKEN")}

    response = requests.get(url, headers=headers)
    data = response.json()

    query = query.lower()
    results = []

    for product in data.get("products", []):

        # Skip concept + archived products
        if product.get("status") != "active":
            continue

        title = product.get("title", "").lower()
        body = product.get("body_html", "").lower()
        tags = " ".join(product.get("tags", [])).lower()

        # match rules
        if query not in title and query not in body and query not in tags:
            continue

        variants = product.get("variants", [])
        main_variant = variants[0] if variants else {}

        price = float(main_variant.get("price", 0) or 0)
        compare_at = float(main_variant.get("compare_at_price") or 0)

        on_sale = compare_at > price
        discount_pct = 0
        if on_sale:
            discount_pct = int(((compare_at - price) / compare_at) * 100)

        inventory = main_variant.get("inventory_quantity", 0)

        if inventory <= 0:
            stock_status = "out"
        elif inventory == 1:
            stock_status = "low"
        elif inventory < 10:
            stock_status = "medium"
        else:
            stock_status = "in"

        results.append({
            "id": product.get("id"),
            "title": product.get("title"),
            "handle": product.get("handle"),
            "price": price,
            "compare_at": compare_at,
            "on_sale": on_sale,
            "discount_pct": discount_pct,
            "image": product.get("image", {}).get("src") if product.get("image") else None,
            "variants_count": len(variants),
            "stock_status": stock_status,
            "inventory": inventory,
	        "created_at": product.get("created_at")
        })

    # --- SORT: newest first (based on Shopify "created_at") ---
    results.sort(key=lambda p: p.get("created_at", ""), reverse=True)

    return results

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
    allow_origins=[
        "https://askyellow.nl",
        "https://www.askyellow.nl",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ],
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
        db = get_db_conn()
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

@app.get("/shopify/search")
def shopify_search(q: str):
    return shopify_search_products(q)

@app.post("/web")
async def web_search(payload: dict):
    query = payload.get("query", "")

    prompt = f"""
    Doe een webzoekopdracht naar echte websites die relevant zijn voor:
    '{query}'.

    Geef ALLEEN het volgende JSON-format terug:
    [
      {{"title": "Titel", "snippet": "Korte beschrijving", "url": "https://..."}},
      ...
    ]

    Geen extra tekst, geen uitleg, geen markdown.
    """

    # --- Nieuwe Responses API call ---
    ai = client.responses.create(
        model="gpt-4.1-mini",
        input=[{"role": "user", "content": prompt}]
    )

    import json

    raw_text = None

    # --- Extract content safely ---
    for block in ai.output:
        try:
            if block.type == "message":
                raw_text = block.content[0].text
                break
        except:
            pass

    if not raw_text:
        return {"results": []}

    # --- Probeerslag 1: Direct JSON ---
    try:
        return {"results": json.loads(raw_text)}
    except:
        pass

    # --- Probeerslag 2: JSON tussen [...] halen ---
    try:
        start = raw_text.index("[")
        end = raw_text.rindex("]") + 1
        cleaned = raw_text[start:end]
        return {"results": json.loads(cleaned)}
    except:
        pass

    # --- Fallback ---
    return {
        "results": [{
            "title": "Webresultaten niet geformatteerd",
            "snippet": raw_text[:250],
            "url": ""
        }]
    }



# =============================================================
# 3. TOOL ENDPOINTS (WEBSEARCH / SHOPIFY / KNOWLEDGE / IMAGE)
# =============================================================

# ---- Websearch Tool (Serper) ----
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

@app.post("/tool/websearch")
async def tool_websearch(payload: dict):
    """Proxy naar Serper API voor webresultaten."""
    query = (payload.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query missing")

    if not SERPER_API_KEY:
        raise HTTPException(status_code=500, detail="SERPER_API_KEY ontbreekt op de server")

    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json",
    }
    body = {"q": query}

    try:
        r = requests.post(url, json=body, headers=headers, timeout=10)
        data = r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Websearch error: {e}")

    results = []
    for item in data.get("organic", [])[:4]:
        results.append({
            "title": item.get("title"),
            "snippet": item.get("snippet"),
            "url": item.get("link"),
        })

    return {
        "tool": "websearch",
        "query": query,
        "results": results,
    }


# ---- Shopify Search Tool 2.0 (title + body + tags + fuzzy) ----
SHOPIFY_STORE = os.getenv("SHOPIFY_STORE_URL")
SHOPIFY_ADMIN_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")


def _extract_search_tokens(query: str) -> set:
    """Zet de gebruikersvraag om in zoektokens + extra kerst/cadeau hints."""
    q = (query or "").lower()
    # basis: woorden
    tokens = set(re.findall(r"[a-z0-9]+", q))

    # fuzzy extras
    if "kerst" in q:
        tokens.add("kerst")
    if "christmas" in q:
        tokens.add("kerst")
        tokens.add("christmas")
    if "cadeau" in q or "kado" in q:
        tokens.update(["cadeau", "gift"])
    if "gift" in q:
        tokens.add("cadeau")

    return tokens


def _score_shopify_product(product: dict, tokens: set) -> int:
    """Geeft een relevanciescore op basis van title, beschrijving, tags, type."""
    title = (product.get("title") or "").lower()
    body = (product.get("body_html") or "").lower()
    tags_raw = (product.get("tags") or "") or ""
    tags = " ".join([t.strip().lower() for t in tags_raw.split(",") if t.strip()])
    ptype = (product.get("product_type") or "").lower()

    combined = " ".join([title, body, tags, ptype])
    score = 0

    for tok in tokens:
        if not tok:
            continue
        if tok in title:
            score += 8
        if tok in tags:
            score += 5
        if tok in ptype:
            score += 3
        if tok in body:
            score += 2

    # extra boost voor kerstproducten
    if "kerst" in tokens and "kerst" in combined:
        score += 10

    return score


@app.post("/tool/shopify_search")
async def tool_shopify_search(payload: dict):
    """Slimme zoektool voor de AskYellow Shopify shop.

    - Zoekt in title, description (body_html), tags en product_type
    - Fuzzy handling van 'kerstcadeau', 'cadeau', 'gift', etc.
    - Sorteert op relevatie + recentheid
    - Fallback: altijd maximaal 5 producten
    """
    query = (payload.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Missing query")

    if not SHOPIFY_STORE or not SHOPIFY_ADMIN_TOKEN:
        raise HTTPException(status_code=500, detail="Shopify env vars ontbreken")

    url = f"https://{SHOPIFY_STORE}/admin/api/2025-10/products.json?limit=250"
    headers = {"X-Shopify-Access-Token": SHOPIFY_ADMIN_TOKEN}

    try:
        r = requests.get(url, headers=headers, timeout=15)
        data = r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Shopify error: {e}")

    products = data.get("products", []) or []
    tokens = _extract_search_tokens(query)

    scored = []
    for p in products:
        # alleen actieve producten
        if p.get("status") != "active":
            continue

        score = _score_shopify_product(p, tokens)
        if score <= 0:
            continue

        variants = p.get("variants") or []
        main_variant = variants[0] if variants else {}
        price = main_variant.get("price")
        compare_at = main_variant.get("compare_at_price")

        try:
            price_f = float(price or 0)
        except Exception:
            price_f = 0.0
        try:
            compare_f = float(compare_at or 0)
        except Exception:
            compare_f = 0.0

        on_sale = compare_f > price_f
        discount_pct = 0
        if on_sale and compare_f:
            discount_pct = int(((compare_f - price_f) / compare_f) * 100)

        result = {
            "id": p.get("id"),
            "title": p.get("title"),
            "handle": p.get("handle"),
            "url": f"https://shop.askyellow.nl/products/{p.get('handle')}",
            "image": (p.get("image") or {}).get("src"),
            "price": price_f if price_f else None,
            "compare_at": compare_f if compare_f else None,
            "discount_pct": discount_pct or None,
            "created_at": p.get("created_at") or "",
            "score": score,
        }
        scored.append(result)

    # Fallback: als niets gescoord heeft, toon dan gewoon de laatste producten
    if not scored:
        for p in products:
            if p.get("status") != "active":
                continue
            variants = p.get("variants") or []
            main_variant = variants[0] if variants else {}
            price = main_variant.get("price")
            compare_at = main_variant.get("compare_at_price")

            try:
                price_f = float(price or 0)
            except Exception:
                price_f = 0.0
            try:
                compare_f = float(compare_at or 0)
            except Exception:
                compare_f = 0.0

            result = {
                "id": p.get("id"),
                "title": p.get("title"),
                "handle": p.get("handle"),
                "url": f"https://shop.askyellow.nl/products/{p.get('handle')}",
                "image": (p.get("image") or {}).get("src"),
                "price": price_f if price_f else None,
                "compare_at": compare_f if compare_f else None,
                "discount_pct": None,
                "created_at": p.get("created_at") or "",
                "score": 1,
            }
            scored.append(result)

    # sorteer: eerst hoogste score, dan nieuwste
    scored.sort(key=lambda x: (x.get("score", 0), x.get("created_at", "")), reverse=True)

    # neem top 5
    top = scored[:5]
    for item in top:
        item.pop("score", None)

    return {
        "tool": "shopify_search",
        "query": query,
        "results": top,
    }


# ---- Knowledge Search Tool ----
@app.post("/tool/knowledge_search")
async def tool_knowledge_search(payload: dict):
    """Maakt gebruik van de bestaande Python knowledge engine."""
    query = (payload.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Missing query")

    # Gebruik de al geladen KNOWLEDGE_ENTRIES + match_question
    kb_answer = match_question(query, KNOWLEDGE_ENTRIES)
    return {
        "tool": "knowledge_search",
        "query": query,
        "answer": kb_answer,
    }


# ---- Image Generation Tool ----

# ===== IMAGE GENERATION AUTH CHECK =====
def require_auth_session(request: Request):
    """Controleer of de gebruiker is ingelogd aan de hand van session-id."""
    session_id = request.headers.get("X-Session-Id") or ""
    if not session_id:
        raise HTTPException(status_code=403, detail="Login vereist voor image generation")

    conn = get_db_conn()
    user = get_user_from_session(conn, session_id)
    conn.close()

    if not user:
        raise HTTPException(status_code=403, detail="Ongeldige of verlopen sessie")

@app.post("/tool/image_generate")
async def tool_image_generate(request: Request, payload: dict):
    require_auth_session(request)

    """Genereert een afbeelding via OpenAI gpt-image-1 model."""
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Missing prompt")

    try:
        result = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size="1024x1024",
        )
        url = result.data[0].url
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image generation error: {e}")

    return {
        "tool": "image_generate",
        "prompt": prompt,
        "url": url,
    }

@app.post("/chat/start")
def chat_start(data: dict):
    session_id = data.get("session_id")
    if not session_id:
        return {"messages": []}

    conn = get_db_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 1️⃣ User ophalen via session_id
    cur.execute(
        "SELECT id FROM users WHERE session_id = %s",
        (session_id,)
    )
    user = cur.fetchone()
    if not user:
        conn.close()
        return {"messages": []}

    # 2️⃣ Laatste conversation ophalen
    cur.execute(
        """
        SELECT id
        FROM conversations
        WHERE user_id = %s
        ORDER BY last_message_at DESC
        LIMIT 1
        """,
        (user["id"],)
    )
    conv = cur.fetchone()
    if not conv:
        conn.close()
        return {"messages": []}

    # 3️⃣ Berichten ophalen
    cur.execute(
        """
        SELECT role, content
        FROM messages
        WHERE conversation_id = %s
        ORDER BY created_at ASC
        """,
        (conv["id"],)
    )
    rows = cur.fetchall()
    conn.close()

    return {
        "messages": [
            {"role": r["role"], "content": r["content"]}
            for r in rows
        ]
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

    # Auth users: aparte tabel voor geregistreerde accounts
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_users (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_login TIMESTAMPTZ
        );
        """
    )

    # User sessions voor ingelogde gebruikers
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_sessions (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
            expires_at TIMESTAMPTZ NOT NULL
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

# Extra uitleg aan het model over beschikbare backend tools
SYSTEM_PROMPT += """
[TOOLCALL RULES]
Je draait binnen YellowMind. De backend heeft eigen tools:
- websearch(query): haal recente webresultaten op.
- shopify_search(query): zoek producten in de AskYellow shop.
- knowledge_search(query): raadpleeg de AskYellow kennisbank.
- image_generate(prompt): genereer een illustratie.

Gebruik deze tools alleen als ze echt helpen.
Verzamel eerst je gedachten, kies dan maximaal de paar meest relevante tools.
Na een tool-call leg je de resultaten in je eigen woorden uit.
"""

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

    # -----------------------------
    # Session ID bepalen
    # -----------------------------
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

    # -----------------------------
    # Safety: geen vraag
    # -----------------------------
    if not question:
        return JSONResponse(
            status_code=400,
            content={"error": "Geen vraag ontvangen."}
        )

    # -----------------------------
    # Init
    # -----------------------------
    final_answer = None
    raw_output = []
    kb_answer = None
    sql_match = None
    hints = {}

    # =============================================================
    # 1. QUICK IDENTITY
    # =============================================================
    identity_answer = try_identity_origin_answer(question, language)
    if identity_answer:
        final_answer = identity_answer

    # =============================================================
    # 2. SQL KNOWLEDGE
    # =============================================================
    if not final_answer:
        sql_match = search_sql_knowledge(question)
        if sql_match and sql_match.get("score", 0) >= 60:
            final_answer = sql_match["answer"]

    # =============================================================
    # 3. JSON KNOWLEDGE ENGINE
    # =============================================================
    if not final_answer:
        try:
            kb_answer = match_question(question, KNOWLEDGE_ENTRIES)
            if kb_answer:
                final_answer = kb_answer
        except Exception:
            kb_answer = None

    hints = detect_hints(question)

    # =============================================================
    # 4. LLM FALLBACK
    # =============================================================
    if not final_answer:
        start_ai = time.time()
        final_answer, raw_output = call_yellowmind_llm(
            question, language, kb_answer, sql_match, hints
        )
        ai_ms = int((time.time() - start_ai) * 1000)
    else:
        ai_ms = 0

    # -----------------------------
    # Final safety
    # -----------------------------
    if not final_answer:
        final_answer = "⚠️ Geen geldig antwoord beschikbaar."

    # =============================================================
    # PERFORMANCE LOGGING (optioneel)
    # =============================================================
    sql_ms = 0
    kb_ms = 0
    total_ms = ai_ms

    try:
        for block in raw_output or []:
            if hasattr(block, "type") and block.type == "response.stats":
                sql_ms = getattr(block, "sql_ms", 0)
                kb_ms = getattr(block, "kb_ms", 0)
                total_ms = getattr(block, "total_ms", ai_ms)
    except Exception:
        pass

    status = detect_cold_start(sql_ms, kb_ms, ai_ms, total_ms)
    print(f"[STATUS] {status} | SQL {sql_ms} ms | KB {kb_ms} ms | AI {ai_ms} ms")

    # =============================================================
    # DATABASE LOGGING (SAFE)
    # =============================================================
    try:
        _log_message_safe(session_id, question, final_answer)
    except Exception as e:
        print("❌ chat_engine logging faalde:", e)

    # =============================================================
    # RESPONSE
    # =============================================================
    return {
        "answer": final_answer,
        "output": raw_output,
        "source": "yellowmind_llm",
        "kb_used": bool(kb_answer),
        "sql_used": bool(sql_match),
        "sql_score": sql_match["score"] if sql_match else None,
        "hints": hints
    }
