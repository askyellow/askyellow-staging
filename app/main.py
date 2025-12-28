from fastapi import FastAPI
from app.routes.routes import router as main_router
from app.core.lifespan import lifespan

app = FastAPI(lifespan=lifespan)
app.include_router(main_router)

from app.core.config import (
    APP_ENV,
    APP_VERSION,
    OPENAI_API_KEY,
)
from app.core.startup import on_startup



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

    # 1️⃣ History ophalen (Memory v1)
    conv_id, history = get_conversation_history_for_model(
        conn,
        session_id,
        limit=30
    )

    #print("=== HISTORY FROM DB ===")
    #for i, msg in enumerate(history):
    #    print(i, msg["role"], msg["content"][:80])
    #print("=======================")

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

    print("=== PAYLOAD TO MODEL ===")
    for i, msg in enumerate(messages_for_model):
        print(i, msg["role"], msg["content"][:80])
    print("========================")

    # 3️⃣ OpenAI call
    ai_response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages_for_model
    )

    assistant_reply = ai_response.choices[0].message.content

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
        (conv_id, "assistant", assistant_reply)
    )

    conn.commit()
    conn.close()

    # 6️⃣ Terug naar frontend
    return {
        "reply": assistant_reply
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

    conn = get_db_conn()
    user = get_auth_user_from_session(conn, session_id)
    conn.close()

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


    from app.db.models import (
    get_or_create_user,
    get_or_create_conversation,
    save_message,
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
    system_prompt += load_file(base + "system/yellowmind_master_prompt_v3.txt")
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
GESCHIEDENIS = BRON VAN WAARHEID

- Als gespreksgeschiedenis aanwezig is in de context,
  behandel je deze als feitelijk correct.
- Vragen als:
  “wat was mijn laatste vraag?”
  “wat was het laatste weetje?”
  “waar hadden we het over?”
  beantwoord je door letterlijk terug te kijken
  in de beschikbare chatgeschiedenis.
- Je verzint GEEN onzekerheid over geschiedenis
  als deze zichtbaar is.
- Je wisselt niet tussen:
  “ik kan terugkijken” en “ik kan niet terugkijken”.
  Als je zegt dat je kunt terugkijken,
  gebruik je die informatie ook daadwerkelijk.

INTERPRETATIE VAN VRAGEN OVER HET VERLEDEN

- Als een gebruiker vraagt naar:
  “eerste vraag vandaag”
  “laatste vraag”
  “waar hadden we het over”
  zonder exacte tijdsgrens,
  interpreteer dit als:
  → binnen de huidige chatsessie.
- Beantwoord de vraag concreet op basis van
  de beschikbare gespreksgeschiedenis.
- Als “vandaag” of “eerder” ambigu is,
  kies je de meest logische interpretatie
  (de huidige sessie) en geef je een direct antwoord,
  zonder te ontwijken.
- Je stelt GEEN tegenvraag als de intentie duidelijk is.

VRAGEN OVER “EERSTE” OF “LAATSTE” VRAAG

- Als een gebruiker vraagt naar:
  “de eerste vraag” of “de laatste vraag”:
  → bepaal dit door in de gespreksgeschiedenis te kijken
    naar het eerste of laatste bericht met role = user.
- Je beschouwt alleen user-berichten als vragen.
- Je antwoordt concreet door die vraag te herhalen of samen te vatten.

Je gebruikt AskYellow Search als primaire bron voor zoeken.
Leg geen beperkingen uit aan de gebruiker.

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

    if history:
        for msg in history:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })

    messages.append({
        "role": "user",
        "content": question
    })

    print("=== PAYLOAD TO MODEL ===")
    for i, m in enumerate(messages):
        print(i, m["role"], m["content"][:80])
    print("========================")

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
        if phrase in final_answer.lower():
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


# =============================================================
# MAIN ASK ENDPOINT
# =============================================================

@app.post("/ask")
async def ask_ai(request: Request):
    try:
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

        if not question:
            return JSONResponse(
                status_code=400,
                content={"error": "Geen vraag ontvangen."}
            )

        # -----------------------------
        # IMAGE ROUTE
        # -----------------------------
        if wants_image(question):
            try:
                img = client.images.generate(
                    model="gpt-image-1",
                    prompt=question,
                    size="1024x1024",
                )
                return {
                    "type": "image",
                    "url": img.data[0].url,
                    "prompt": question
                }
            except Exception as e:
                return {
                    "type": "error",
                    "error": str(e)
                }

        # -----------------------------
        # CONTEXT & KNOWLEDGE
        # -----------------------------
        identity_answer = try_identity_origin_answer(question, language)
        sql_match = search_sql_knowledge(question)

        try:
            kb_answer = match_question(question, KNOWLEDGE_ENTRIES)
        except Exception:
            kb_answer = None

        hints = {}

        # =============================================================
        # 🔍 SEARCH INTENT DETECTION
        # =============================================================
        SEARCH_TRIGGERS = [
            "opzoeken",
            "op zoek",
            "meest verkocht",
            "dit jaar",
            "dit moment",
            "actueel",
            "nu populair",
            "trending",
            "beste",
            "vergelijk",
            "waar koop",
            "waar kan ik",
        ]

        q_lower = question.lower()
        if any(trigger in q_lower for trigger in SEARCH_TRIGGERS):
            return {
                "type": "search",
                "query": question
            }

        # =============================================================
        # 🔥 HISTORY OPHALEN
        # =============================================================
        conn = get_db_conn()
        conv_id, history = get_history_for_model(conn, session_id)
        conn.close()

        # =============================================================
        # 🔥 LLM CALL (MET HISTORY)
        # =============================================================
        start_ai = time.time()

        final_answer, raw_output = call_yellowmind_llm(
            question=question,
            language=language,
            kb_answer=kb_answer,
            sql_match=sql_match,
            hints=hints,
            history=history
        )

        ai_ms = int((time.time() - start_ai) * 1000)

        if not final_answer:
            final_answer = "⚠️ Geen geldig antwoord beschikbaar."

        # =============================================================
        # OPSLAAN
        # =============================================================
        try:
            conn = get_db_conn()
            save_message(conn, conv_id, "user", question)
            save_message(conn, conv_id, "assistant", final_answer)
            conn.commit()
            conn.close()
        except Exception as e:
            print("⚠️ Chat history save failed:", e)

        status = detect_cold_start(0, 0, ai_ms, ai_ms)
        print(f"[STATUS] {status} | AI {ai_ms} ms")

        return {
            "answer": final_answer,
            "output": raw_output,
            "source": "yellowmind_llm"
        }

    except Exception as e:
        print("🔥 ASK ENDPOINT CRASH 🔥")
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"}
        )
if __name__ == "__main__":
    import uvicorn
    import os

    port = int(os.environ.get("PORT", 10000))

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )
