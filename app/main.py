from fastapi import FastAPI
from app.routes.routes import router as main_router
from app.core.lifespan import lifespan
from app.core.config import APP_ENV, APP_VERSION
from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException
from app.core.startup import get_knowledge_entries


import os
import requests
import re

from app.routes.ask import router as ask_router
app.include_router(ask_router)



from app.core.config import (
    APP_ENV,
    APP_VERSION,
    OPENAI_API_KEY,
)
from app.core.startup import on_startup

from app.db.models import (
    get_or_create_user,
    get_or_create_conversation,
    save_message,
)

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

from app.yellowmind.knowledge_engine import load_knowledge, match_question
from app.yellowmind.identity_origin import try_identity_origin_answer


# =============================================================
# 1. ENVIRONMENT & OPENAI CLIENT
# =============================================================



# =============================================================
# 2. FASTAPI APP & CORS
# =============================================================

app = FastAPI(title="YellowMind API")

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
    kb_answer = match_question(query, get_knowledge_entries())
    return {
        "tool": "knowledge_search",
        "query": query,
        "answer": kb_answer,
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
def startup_event():
    on_startup()

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


   

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



if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 10000))

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )
