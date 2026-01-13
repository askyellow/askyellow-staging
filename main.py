from pyexpat.errors import messages
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from dotenv import load_dotenv
from openai import OpenAI
from chat_engine.routes import router as chat_router
from fastapi.responses import FileResponse
from fastapi import Request
from core.time import TimeContext

import os
import uvicorn
import requests
import unicodedata
import re
import secrets
import resend
from datetime import datetime, timedelta
import uuid
import traceback

# DB
import psycopg2
import psycopg2.extras
from psycopg2.extras import RealDictCursor
# chat
from chat_engine.db import get_conn
from chat_engine.utils import get_logical_date

from fastapi import APIRouter, Request
from passlib.context import CryptContext

from passlib.context import CryptContext
from core.time_context import TimeContext


TIME_CONTEXT = TimeContext()

answer = (
    f"Vandaag is het {TIME_CONTEXT.today_string()} "
    f"en het is nu {TIME_CONTEXT.time_string()}."
)

TIME_CONTEXT = TimeContext()

pwd_context = CryptContext(
    schemes=["bcrypt_sha256", "scrypt"],
    deprecated="auto"
)

resend.api_key = os.getenv("RESEND_API_KEY")

def normalize_password(password: str) -> str:
    if not password:
        return ""
    return password.strip()

def run_websearch_internal(query: str) -> list:
    """
    Interne helper die dezelfde logica gebruikt als /tool/websearch
    maar dan direct in Python.
    """
    if not query or not SERPER_API_KEY:
        return []

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
        print("⚠️ Internal websearch error:", e)
        return []

    results = []
    for item in data.get("organic", [])[:3]:
        results.append({
            "title": item.get("title"),
            "snippet": item.get("snippet"),
            "url": item.get("link"),
        })

    return results

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
# 2. FASTAPI APP & CORS
# =============================================================

app = FastAPI(title="YellowMind API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://www.askyellow.nl",
        "https://askyellow.nl",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
# CHAT HISTORY – VOOR MODEL CONTEXT (BLOK 1) NIEUW!!!
# =============================================================

def get_history_for_model(conn, session_id, limit=30):
    """
    Haalt de LAATSTE berichten van een gesprek op,
    bedoeld voor LLM-context (oud → nieuw).
    """
    cur = conn.cursor()

    auth_user = get_auth_user_from_session(conn, session_id)
    owner_id = (
        get_or_create_user_for_auth(conn, auth_user["id"], session_id)
        if auth_user
        else get_or_create_user(conn, session_id)
    )

    conv_id = get_or_create_conversation(conn, owner_id)

    cur.execute(
        """
        SELECT role, content
        FROM messages
        WHERE conversation_id = %s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (conv_id, limit)
    )

    rows = cur.fetchall()
    rows.reverse()  # 🔥 cruciaal: oud → nieuw voor het model

    return conv_id, rows


@app.get("/chat")
def serve_chat_page():
    base = os.path.dirname(os.path.abspath(__file__))
    return FileResponse(os.path.join(base, "static/chat/chat.html"))

@app.get("/chat/history")
async def chat_history(session_id: str):
    conn = get_db_conn()
    cur = conn.cursor()

    auth_user = get_auth_user_from_session(conn, session_id)

    if auth_user:
        owner_id = get_or_create_user_for_auth(conn, auth_user["id"], session_id)
    else:
        owner_id = get_or_create_user(conn, session_id)

    conv_id = get_or_create_conversation(conn, owner_id)

    cur.execute(
        """
        SELECT role, content
        FROM messages
        WHERE conversation_id = %s
        ORDER BY created_at ASC
        """,
        (conv_id,)
    )

    rows = cur.fetchall()
    conn.close()

    return {
        "messages": [
            {"role": r["role"], "content": r["content"]}
            for r in rows
        ]
    }

def get_conversation_history_for_model(conn, session_id, limit=12):
    cur = conn.cursor()

    auth_user = get_auth_user_from_session(conn, session_id)
    owner_id = (
        get_or_create_user_for_auth(conn, auth_user["id"], session_id)
        if auth_user
        else get_or_create_user(conn, session_id)
    )

    conv_id = get_or_create_conversation(conn, owner_id)

    cur.execute(
        """
        SELECT role, content
        FROM messages
        WHERE conversation_id = %s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (conv_id, limit)
    )

    rows = list(reversed(cur.fetchall()))
    return conv_id, rows



    owner_id = get_or_create_user_for_auth(conn, auth_user["id"], session_id)

    conv_id = get_or_create_conversation(conn, owner_id)

    cur.execute(
        """
        SELECT role, content
        FROM messages
        WHERE conversation_id = %s
        ORDER BY created_at DESC
        """,
        (conv_id,)
    )

    rows = cur.fetchall()
    conn.close()

    messages = [{"role": r[0], "content": r[1]} for r in rows]
    return {"messages": messages}

def store_message_pair(session_id, user_text, assistant_text):
    try:
        conn = get_db_conn()
        conv_id, _ = get_history_for_model(conn, session_id)
        save_message(conn, conv_id, "user", user_text)
        save_message(conn, conv_id, "assistant", assistant_text)
        conn.commit()
        conn.close()
    except Exception as e:
        print("⚠️ History save failed:", e)


@app.post("/chat")
async def chat(payload: dict):
    session_id = payload.get("session_id")
    user_input = payload.get("message", "").strip()

    if not session_id or not user_input:
        raise HTTPException(
            status_code=400,
            detail="session_id of message ontbreekt"
        )

    conn = get_db_conn()
    cur = conn.cursor()

    # 1️⃣ History ophalen
    conv_id, history = get_conversation_history_for_model(
        conn,
        session_id,
        limit=30
    )

    # 2️⃣ Payload voor model bouwen
    messages_for_model = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        }
    ]

    for msg in history:
        messages_for_model.append({
            "role": msg["role"],
            "content": msg["content"]
        })

    messages_for_model.append({
        "role": "user",
        "content": user_input
    })

    # absolute noodrem
    messages = messages[:20]


    # 3️⃣ OpenAI call
    ai_response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages_for_model,
        max_tokens=500
    )

    answer = extract_text_from_response(ai_response)

    if not answer:
        answer = "⚠️ Ik kreeg geen inhoudelijk antwoord terug, maar de chat werkt wel 🙂"

    # 4️⃣ Opslaan: user message
    cur.execute(
        """
        INSERT INTO messages (conversation_id, role, content)
        VALUES (%s, %s, %s)
        """,
        (conv_id, "user", user_input)
    )

    # 5️⃣ Opslaan: assistant reply
    cur.execute(
        """
        INSERT INTO messages (conversation_id, role, content)
        VALUES (%s, %s, %s)
        """,
        (conv_id, "assistant", answer)
    )

    conn.commit()
    conn.close()

    # 6️⃣ Terug naar frontend
    return {
        "reply": answer
    }




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
    # 👇 PRE-FLIGHT ALTIJD TOESTAAN
    if request.method == "OPTIONS":
        return

    session_id = request.headers.get("X-Session-Id") or ""
    if not session_id:
        raise HTTPException(
            status_code=403,
            detail="Login vereist voor image generation"
        )

    
    if not user:
        raise HTTPException(
            status_code=403,
            detail="Ongeldige of verlopen sessie"
        )


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
        print("🔥 IMAGE GENERATION ERROR 🔥")
        print(traceback.format_exc())
        raise HTTPException(
        status_code=500,
        detail=str(e)
    )

    return {
        "tool": "image_generate",
        "prompt": prompt,
        "url": url,
    }
def detect_intent(text: str) -> str:
    if re.search(r"(afbeelding|image|plaatje|genereer|maak.*(afbeelding|image))", text, re.I):
        return "image"
    if re.search(r"(zoek|zoeken|opzoeken)", text, re.I):
        return "search"
    return "text"

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

def get_recent_messages(conversation_id, limit=12):
    """
    Haal de laatste berichten van een gesprek op
    (oud → nieuw), voor model-context.
    """
    conn = get_db_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT role, content
        FROM messages
        WHERE conversation_id = %s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (conversation_id, limit)
    )

    rows = cur.fetchall()
    conn.close()
    return rows


@app.on_event("startup")
def on_startup():
    # Zorg dat de tabellen bestaan bij het starten van de app
    init_db()

    from passlib.context import CryptContext


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


@app.post("/auth/login")
async def login(payload: dict):
    email = (payload.get("email") or "").lower().strip()
    password = payload.get("password") or ""

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email en wachtwoord verplicht")

    conn = get_db_conn()
    cur = conn.cursor()

    # gebruiker ophalen
    cur.execute(
        "SELECT id, password_hash, first_name FROM auth_users WHERE email = %s",
        (email,)
    )
    user = cur.fetchone()

    if not user or not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # nieuwe sessie
    session_id = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(days=7)

    cur.execute(
        """
        INSERT INTO user_sessions (session_id, user_id, expires_at)
        VALUES (%s, %s, %s)
        """,
        (session_id, user["id"], expires_at)
    )

    cur.execute(
        "UPDATE auth_users SET last_login = NOW() WHERE id = %s",
        (user["id"],)
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "session": session_id,
        "first_name": user["first_name"]
    }


def get_auth_user_from_session(conn, session_id: str):
    cur = conn.cursor()
    cur.execute("""
        SELECT au.id, au.first_name
        FROM user_sessions us
        JOIN auth_users au ON au.id = us.user_id
        WHERE us.session_id = %s
          AND us.expires_at > NOW()
    """, (session_id,))

    row = cur.fetchone()
    if not row:
        return None

    return {
    "id": row["id"],
    "first_name": row["first_name"]
}


def get_or_create_user_for_auth(conn, auth_user_id: int, session_id: str):
    cur = conn.cursor()
    stable_sid = f"auth-{auth_user_id}"

    cur.execute(
        "SELECT id FROM users WHERE session_id = %s",
        (stable_sid,)
    )
    row = cur.fetchone()
    if row:
        return row["id"]

    cur.execute(
        """
        INSERT INTO users (session_id)
        VALUES (%s)
        RETURNING id
        """,
        (stable_sid,)
    )
    user_id = cur.fetchone()["id"]
    conn.commit()
    return user_id

    cur.execute(
        """
        INSERT INTO users (session_id)
        VALUES (%s)
        RETURNING id
        """,
        (stable_sid,)
    )
    conn.commit()
    row = cur.fetchone()
    row = cur.fetchone()
    return row[0]


    # 2) Anders maken we 'm aan
    cur.execute(
        """
        INSERT INTO users (session_id)
        VALUES (%s)
        RETURNING id
        """,
        (stable_sid,),
    )
    conn.commit()
    row = cur.fetchone()
    return row["id"] if not isinstance(row, dict) else row["id"]

@app.post("/auth/register")
async def register(payload: dict):
    email = (payload.get("email") or "").lower().strip()
    password = payload.get("password") or ""
    first_name = (payload.get("first_name") or "").strip()
    last_name = (payload.get("last_name") or "").strip()

    if not email or not password or not first_name or not last_name:
        raise HTTPException(status_code=400, detail="Alle velden zijn verplicht")

    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Wachtwoord te kort")

    conn = get_db_conn()
    cur = conn.cursor()

    # bestaat email al?
    cur.execute("SELECT id FROM auth_users WHERE email = %s", (email,))
    if cur.fetchone():
        conn.close()
        raise HTTPException(status_code=409, detail="Email bestaat al")

    safe_password = normalize_password(password)
    password_hash = pwd_context.hash(safe_password)
    pwd_context.verify(password, password_hash)


    # gebruiker aanmaken
    cur.execute(
        """
        INSERT INTO auth_users (email, password_hash, first_name, last_name)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (email, password_hash, first_name, last_name)
    )
    user_id = cur.fetchone()["id"]

    # auto-login sessie
    session_id = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(days=7)

    cur.execute(
        """
        INSERT INTO user_sessions (session_id, user_id, expires_at)
        VALUES (%s, %s, %s)
        """,
        (session_id, user_id, expires_at)
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "session": session_id,
        "first_name": first_name
    }
@app.post("/auth/request-password-reset")
async def request_password_reset(payload: dict):
    email = (payload.get("email") or "").lower().strip()

    conn = get_db_conn()
    cur = conn.cursor()

    cur.execute(
        "SELECT id FROM auth_users WHERE email = %s",
        (email,)
    )
    user = cur.fetchone()

    if user:
        token = str(uuid.uuid4())
        expires = datetime.utcnow() + timedelta(minutes=30)

        cur.execute(
            """
            UPDATE auth_users
            SET reset_token = %s,
                reset_expires = %s
            WHERE id = %s
            """,
            (token, expires, user["id"])
        )

        conn.commit()

        reset_link = f"https://askyellow.nl/reset.html?token={token}"

        try:
            resend.Emails.send({
    "from": "AskYellow <no-reply@askyellow.nl>",
    "to": email,
    "subject": "Reset je wachtwoord voor AskYellow",
    "html": f"""
        <p>Hoi,</p>

        <p>Via onderstaande link kun je een nieuw wachtwoord instellen:</p>

        <p>
          <a href="{reset_link}">
            Reset je wachtwoord
          </a>
        </p>

        <p>Deze link is <strong>30 minuten geldig</strong>.</p>

        <p>Groet,<br>
        YellowMind</p>
    """
})

        except Exception as e:
            # fallback: log link als mail faalt
            print("❌ MAIL FAILED — RESET LINK:", reset_link)
            print(e)

    conn.close()

    # ⚠️ altijd hetzelfde antwoord (security)
    return {
        "message": "Als dit e-mailadres bestaat, ontvang je een reset-link."
    }
@app.post("/auth/reset-password")
async def reset_password(payload: dict):
    token = payload.get("token")
    new_password = payload.get("password")

    if not token or not new_password:
        raise HTTPException(status_code=400, detail="Token en nieuw wachtwoord verplicht")

    conn = get_db_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id
        FROM auth_users
        WHERE reset_token = %s
          AND reset_expires > NOW()
        """,
        (token,)
    )
    user = cur.fetchone()

    if not user:
        raise HTTPException(status_code=400, detail="Ongeldige of verlopen reset-link")

    # 🔑 HIER gaat het NU goed
    new_hash = pwd_context.hash(new_password)

    cur.execute(
        """
        UPDATE auth_users
        SET password_hash = %s,
            reset_token = NULL,
            reset_expires = NULL
        WHERE id = %s
        """,
        (new_hash, user["id"])
    )

    conn.commit()
    conn.close()

    return {"success": True}


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

def get_or_create_conversation(conn, owner_id: int):
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id
        FROM conversations
        WHERE user_id = %s
        ORDER BY started_at DESC
        LIMIT 1
        """,
        (owner_id,)
    )
    row = cur.fetchone()
    if row:
        return row["id"]

    cur.execute(
        """
        INSERT INTO conversations (user_id)
        VALUES (%s)
        RETURNING id
        """,
        (owner_id,)
    )
    conn.commit()
    row = cur.fetchone()
    return row["id"]

    cur.execute(
        """
        INSERT INTO conversations (user_id)
        VALUES (%s)
        RETURNING id
        """,
        (owner_id,),
    )

    conn.commit()
    return cur.fetchone()[0]

       
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
            print("⚠ SQL STATUS:", resp.status_code)
            return None
        data = resp.json()
    except Exception as e:
        print("⚠ SQL ERROR:", e)
        return None

    best = None
    best_score = 0

    for row in data:
        # 🔒 robuust: werkt voor dict én string
        row_question = (
            row.get("question") if isinstance(row, dict)
            else row
        )

        score = compute_match_score(question, row_question or "")

        if score > best_score:
            best_score = score
            best = {
                "id": row.get("id") if isinstance(row, dict) else None,
                "question": row_question or "",
                "answer": row.get("answer") if isinstance(row, dict) else "",
                "score": score
            }

    # ⬅️ DIT hoort nog binnen de functie
    if best:
        print(f"🤖 SQL BEST MATCH SCORE={best_score}")
        return best

    return None


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
# IMAGE INTENT DETECTION
# =============================================================

def wants_image(q: str) -> bool:
    triggers = [
        "genereer",
        "afbeelding",
        "plaatje",
        "beeld",
        "image",
        "illustratie",
    ]
    return any(t in q.lower() for t in triggers)


# =============================================================
# 6. OPENAI CALL — FIXED FOR o3 RESPONSE FORMAT (SAFE)
# =============================================================

def call_yellowmind_llm(
    question,
    language,
    kb_answer,
    sql_match,
    hints,
    history=None
):
   
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        }
    ]
    if hints and hints.get("time_context"):
        messages.append({
            "role": "system",
            "content": hints["time_context"]
        })

    if hints and hints.get("web_context"):
        messages.append({
            "role": "system",
            "content": hints["web_context"]
        })
# Conversatiegeschiedenis (LLM-context)
    if history:
        for msg in history:
            content = msg.get("content")

            # 🚫 alleen strings
            if not isinstance(content, str):
                continue

            # 🚫 images nooit naar het model
            if content.startswith("[IMAGE]"):
                continue

            messages.append({
                "role": msg.get("role", "user"),
                "content": content[:2000]  # harde safety cap
        })

    

    # 🔹 User vraag
    messages.append({
        "role": "user",
        "content": question
    })

    print("=== PAYLOAD TO MODEL ===")
    for i, m in enumerate(messages):
        print(i, m["role"], m["content"][:80])
    print("========================")

    import json

    print("🔴 MESSAGE COUNT:", len(messages))
    print("🔴 FIRST MESSAGE:", messages[0])
    print("🔴 LAST MESSAGE:", messages[-1])
    print("🔴 RAW SIZE:", len(json.dumps(messages)))

    for i, m in enumerate(messages):
        size = len(m.get("content", ""))
        if size > 5000:
            print(f"🚨 MESSAGE {i} ROLE={m['role']} SIZE={size}")

    print("MAX MESSAGE SIZE:", max(len(m["content"]) for m in messages))


    ai = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages
    )

    final_answer = ai.choices[0].message.content

    # 🔒 Airbag: verboden zinnen filteren
    BANNED_PHRASES = [
        "geen toegang",
        "geen toegang heb",
        "geen toegang heeft",
        "niet rechtstreeks opzoeken",
        "kan dat niet opzoeken",
        "kan dit niet opzoeken",
        "live websearch",
        "realtime websearch",
        "websearch",
        "internet",
        "online opzoeken",
        "als ai",
        "sorry",
    ]

    lower_answer = final_answer.lower()

    for phrase in BANNED_PHRASES:
        if phrase in lower_answer:
            final_answer = (
                "Ik help je hier graag bij. "
                "Kun je iets specifieker aangeven wat je zoekt?"
            )
            break

    return final_answer, []




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

# -----------------------------
# IMAGE ROUTE
# -----------------------------
def generate_image(prompt: str) -> str:
    result = client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size="1024x1024"
    )

    # 🔎 Log volledige response (tijdelijk)
    print("IMAGE RESPONSE:", result)

    # ✅ Veilig ophalen
    if result.data and len(result.data) > 0:
        image = result.data[0]

        # Sommige SDK's gebruiken .url, andere .b64_json
        if hasattr(image, "url") and image.url:
            return image.url

        if hasattr(image, "b64_json") and image.b64_json:
            return f"data:image/png;base64,{image.b64_json}"

    # ❌ Fallback
    return None


# =============================================================
# MAIN ASK ENDPOINT
# =============================================================


@app.post("/ask")
async def ask(request: Request):
    payload = await request.json()

    question = payload.get("question")
    session_id = payload.get("session_id")
    language = payload.get("language", "nl")

    # -----------------------------
    # AUTH
    # -----------------------------
    conn = get_db_conn()
    user = get_auth_user_from_session(conn, session_id)
    conn.close()

    intent = detect_intent(question)

    # 🕒 TIJDVRAGEN — DIRECT NA INTENT
    TIME_KEYWORDS = [
        "vandaag",
        "welke dag is het",
        "wat voor dag is het",
        "laatste jaarwisseling",
        "afgelopen jaarwisseling",
    ]

    is_time_question = any(k in question.lower() for k in TIME_KEYWORDS)

    if is_time_question:
        answer = f"Vandaag is het {TIME_CONTEXT.today_string()}."
        store_message_pair(session_id, question, answer)
        return {
            "type": "text",
            "answer": answer
        }

    # =============================================================
    # 🖼 IMAGE
    # =============================================================
    if intent == "image":
        image_url = generate_image(question)

        if not image_url:
            answer = "⚠️ Afbeelding genereren mislukt."
            store_message_pair(session_id, question, answer)
            return {"type": "error", "answer": answer}

        store_message_pair(session_id, question, f"[IMAGE]{image_url}")
        return {"type": "image", "url": image_url}


        image_url = generate_image(question)

        if not image_url:
            answer = "⚠️ Afbeelding genereren mislukt. Probeer het opnieuw."
            store_message_pair(session_id, question, answer)
            return {
                "type": "error",
                "answer": answer
            }

        store_message_pair(session_id, question, f"[IMAGE]{image_url}")
        return {
            "type": "image",
            "url": image_url
        }

    # =============================================================
    # 🔍 SEARCH
    # =============================================================
    if intent == "search":
        intent = "text"

    # -----------------------------
    # 💬 TEXT
    # -----------------------------
    conn = get_db_conn()
    _, history = get_history_for_model(conn, session_id)
    conn.close()

    from search.web_context import build_web_context

    web_results = run_websearch_internal(question)
    web_context = build_web_context(web_results)

    hints = {
        "time_context": TIME_CONTEXT.system_prompt(),
        "web_context": web_context
    }

    final_answer, _ = call_yellowmind_llm(
        question=question,
        language=language,
        kb_answer=None,
        sql_match=None,
        hints=hints,
        history=history
    )

    if not final_answer:
        final_answer = "⚠️ Ik kreeg geen inhoudelijk antwoord terug, maar de chat werkt wel 🙂"

    store_message_pair(session_id, question, final_answer)

    return {
        "type": "text",
        "answer": final_answer
    }




   

