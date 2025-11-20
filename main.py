from fastapi import FastAPI, Request
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
    print("WARNING: No YELLOWMIND_MODEL env found → fallback to o3-mini")
    YELLOWMIND_MODEL = "o3-mini"

VALID_MODELS = [
    "o3-mini",
    "o1-mini",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4o-mini",
]

if YELLOWMIND_MODEL not in VALID_MODELS:
    print(f"WARNING: Unknown model '{YELLOWMIND_MODEL}' → fallback to o3-mini")
    YELLOWMIND_MODEL = "o3-mini"

print(f"Yellowmind using model: {YELLOWMIND_MODEL}")

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
    allow_origins=["*"],
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
        print(f"WARNING: Yellowmind config file not found: {full_path}")
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
            print("SQL STATUS:", resp.status_code)
            return None
        data = resp.json()
    except Exception as e:
        print("SQL ERROR:", e)
        return None

    best = None
    best_score = 0

    for row in data:
        score = compute_match_score(question, row.get("question", ""))
        if score > best_score:
            best_score = score
            best = {
                "id": row.get("id"),
                "question": row.get("question", ""),
                "answer": row.get("answer", ""),
                "score": score
            }

    if best:
        print(f"[SQL-MATCH] score={best_score}")
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
# 6. OPENAI CALL — SAFE PARSER + AI/EXT TIMING
# =============================================================

def call_yellowmind_llm(question, language, kb_answer, sql_match, hints):
    messages = []

    # SYSTEM
    messages.append({"role": "system", "content": SYSTEM_PROMPT})

    # KNOWLEDGE BLOCKS
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
        messages.append({
            "role": "system",
            "content": "[ASKYELLOW_KNOWLEDGE]\n" + "\n\n".join(knowledge_blocks)
        })

    # HINTS
    if hints:
        hint_text = "\n".join([f"- {k}: {v}" for k, v in hints.items() if v])
        messages.append({"role": "system", "content": "[BACKEND_HINTS]\n" + hint_text})

    # USER
    messages.append({"role": "user", "content": question})

    selected_model = YELLOWMIND_MODEL
    print(f"Model selected: {selected_model}")

    # AI CALL TIMING
    t_ai_start = time.perf_counter()
    llm_response = client.responses.create(
        model=selected_model,
        input=messages
    )
    t_ai_end = time.perf_counter()

    # PARSE OUTPUT
    answer_text = None
    t_parse_start = time.perf_counter()

    try:
        output = getattr(llm_response, "output", None)

        if isinstance(output, list):
            for block in output:
                content = getattr(block, "content", None)
                if isinstance(content, list) and len(content) > 0:
                    first = content[0]
                    text = getattr(first, "text", None)
                    if text:
                        answer_text = text
                        break

        # fallback for some clients
        if not answer_text and hasattr(llm_response, "output_text"):
            answer_text = llm_response.output_text

    except Exception as e:
        print("EXTRACT ERROR:", e)

    t_parse_end = time.perf_counter()

    ai_ms = (t_ai_end - t_ai_start) * 1000
    ext_ms = (t_parse_end - t_ai_end) * 1000
    print(f"[AI]   {ai_ms:.2f} ms")
    print(f"[EXT]  {ext_ms:.2f} ms")

    if not answer_text:
        answer_text = "Ik kon het antwoord niet verwerken."

    # JSON-safe raw output
    try:
        raw = llm_response.model_dump()
        raw_output = raw.get("output", [])
    except Exception:
        raw_output = []

    return answer_text, raw_output

# =============================================================
# 7. ENDPOINTS
# =============================================================

@app.get("/")
async def root():
    return {"status": "ok", "message": "Yellowmind backend is running"}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.head("/")
async def head_root():
    return Response(status_code=200)

@app.post("/ask")
async def ask_ai(request: Request):
    t_total_start = time.perf_counter()

    data = await request.json()
    question = (data.get("question") or "").strip()
    language = (data.get("language") or "nl").lower()

    if not question:
        return JSONResponse(
            status_code=400,
            content={"error": "Geen vraag ontvangen."},
        )

    # QUICK IDENTITY
    identity_answer = try_identity_origin_answer(question, language)
    if identity_answer:
        t_total_ms = (time.perf_counter() - t_total_start) * 1000
        print(f"[TOTAL] {t_total_ms:.2f} ms (identity)")
        return {
            "answer": identity_answer,
            "output": [],
            "source": "identity_origin",
            "kb_used": False,
            "sql_used": False,
            "sql_score": None,
            "hints": {}
        }

    # SQL KNOWLEDGE
    t_sql_start = time.perf_counter()
    sql_match = search_sql_knowledge(question)
    t_sql_ms = (time.perf_counter() - t_sql_start) * 1000
    print(f"[SQL]  {t_sql_ms:.2f} ms")

    if sql_match and sql_match["score"] >= 60:
        t_total_ms = (time.perf_counter() - t_total_start) * 1000
        print(f"[TOTAL] {t_total_ms:.2f} ms (sql direct hit)")
        return {
            "answer": sql_match["answer"],
            "output": [],
            "source": "sql",
            "kb_used": False,
            "sql_used": True,
            "sql_score": sql_match["score"],
            "hints": {}
        }

    # JSON KNOWLEDGE ENGINE
    t_kb_start = time.perf_counter()
    try:
        kb_answer = match_question(question, KNOWLEDGE_ENTRIES)
    except Exception:
        kb_answer = None
    t_kb_ms = (time.perf_counter() - t_kb_start) * 1000
    print(f"[KB]   {t_kb_ms:.2f} ms")

    hints = detect_hints(question)

    # AI LAYER
    final_answer, raw_output = call_yellowmind_llm(
        question, language, kb_answer, sql_match, hints
    )

    t_total_ms = (time.perf_counter() - t_total_start) * 1000
    print(f"[TOTAL] {t_total_ms:.2f} ms")

    return {
        "answer": final_answer,
        "output": raw_output,
        "source": "yellowmind_llm",
        "kb_used": bool(kb_answer),
        "sql_used": bool(sql_match),
        "sql_score": sql_match["score"] if sql_match else None,
        "hints": hints
    }

# =============================================================
# 8. LOCAL DEV
# =============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
