from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from dotenv import load_dotenv
from openai import OpenAI
import os
import uvicorn
import requests
import time
import unicodedata
import re

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
# 6. OPENAI CALL — FIXED FOR o3 RESPONSE FORMAT
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
        hint_text = "\n".join([f"- {k}: {v}" for k, v in hints.items() if v])
        messages.append({"role": "system", "content": "[BACKEND_HINTS]\n" + hint_text})

    messages.append({"role": "user", "content": question})

    primary_model = YELLOWMIND_MODEL
    fallback_model = None
    if primary_model in ["gpt-4.1", "gpt-4.1-mini"]:
        fallback_model = "gpt-4o-mini"

    print(f"🤖 Model geselecteerd (primary): {primary_model}")
    if fallback_model:
        print(f"🧠 Fallback model geconfigureerd: {fallback_model}")

    llm_start = time.perf_counter()
    used_model = primary_model
    llm_response = None

    try:
        if fallback_model:
            print(f"⚡ Trying primary model: {primary_model}")
            t0 = time.perf_counter()
            llm_response = client.responses.create(
                model=primary_model,
                input=messages
            )
            primary_dur = time.perf_counter() - t0

            if primary_dur > 6.0:
                print(f"⚠️ {primary_model} te traag ({primary_dur:.2f}s), switching to {fallback_model}")
                print(f"🧠 Trying fallback model: {fallback_model}")
                t1 = time.perf_counter()
                llm_response = client.responses.create(
                    model=fallback_model,
                    input=messages
                )
                fallback_dur = time.perf_counter() - t1
                used_model = fallback_model
                print(f"🧠 Fallback {fallback_model} success in {fallback_dur:.2f}s")
            else:
                print(f"🧠 Primary model {primary_model} success in {primary_dur:.2f}s")
        else:
            print(f"🤖 Using single model: {primary_model}")
            llm_response = client.responses.create(
                model=primary_model,
                input=messages
            )
    except Exception as e:
        print("❌ LLM CALL ERROR:", e)
        llm_total = time.perf_counter() - llm_start
        return "⚠️ Ik kon geen geldig antwoord genereren.", [], llm_total

    llm_total = time.perf_counter() - llm_start

    try:
        assistant_block = llm_response.output[1]
        answer_text = assistant_block.content[0].text
    except Exception as e:
        print("❌ EXTRACT ERROR:", e)
        answer_text = "⚠️ Ik kon het antwoord niet verwerken."

    print(f"[LLM] Gebruikt model: {used_model}")
    return answer_text, llm_response.output, llm_total


# =============================================================
# 7. ENDPOINTS
# =============================================================

@app.get("/")
async def root():
    return {"status": "ok", "message": "Yellowmind backend draait 🚀"}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.head("/")
async def head_root():
    return Response(status_code=200)


@app.post("/ask")
async def ask_ai(request: Request):
    req_start = time.perf_counter()
    print("\n======== NEW REQUEST ========")

    data = await request.json()
    question = (data.get("question") or "").strip()
    language = (data.get("language") or "nl").lower()

    print(f"Vraag: {question}")

    if not question:
        print("⚠️ Geen vraag ontvangen.")
        total = time.perf_counter() - req_start
        print(f"[Perf] TOTAL REQUEST: {total:.4f} sec")
        print("==========================================\n")
        return JSONResponse(
            status_code=400,
            content={"error": "Geen vraag ontvangen."},
        )

    # Identity-origin
    t_id_start = time.perf_counter()
    identity_answer = try_identity_origin_answer(question, language)
    t_id = time.perf_counter() - t_id_start
    print(f"[Perf] Identity-origin: {t_id:.4f} sec")

    if identity_answer:
        print("[Source] identity_origin (direct antwoord)")
        total = time.perf_counter() - req_start
        print("[Perf] OpenAI LLM: 0.0000 sec")
        print(f"[Perf] TOTAL REQUEST: {total:.4f} sec")
        print("==========================================\n")
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
    t_sql = time.perf_counter() - t_sql_start
    print(f"[Perf] SQL Search: {t_sql:.4f} sec")

    if sql_match:
        print(f"[SQL] Best match score: {sql_match['score']} / 100")
        print(f"[SQL] Q: {sql_match['question']}")
    else:
        print("[SQL] Geen match gevonden")

    if sql_match and sql_match["score"] >= 60:
        print("[Source] sql (direct hit)")
        total = time.perf_counter() - req_start
        print("[Perf] OpenAI LLM: 0.0000 sec")
        print(f"[Perf] TOTAL REQUEST: {total:.4f} sec")
        print("==========================================\n")
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
    except Exception as e:
        print("KB error:", e)
        kb_answer = None
    t_kb = time.perf_counter() - t_kb_start
    print(f"[Perf] JSON KB: {t_kb:.4f} sec")
    if kb_answer:
        print("[KB] JSON KB match actief")
    else:
        print("[KB] Geen JSON KB match")

    # HINTS
    t_hint_start = time.perf_counter()
    hints = detect_hints(question)
    t_hint = time.perf_counter() - t_hint_start
    print(f"[Perf] Hint detection: {t_hint:.4f} sec")
    print(f"[HINT] {hints}")

    # LLM CALL
    final_answer, raw_output, llm_dur = call_yellowmind_llm(
        question, language, kb_answer, sql_match, hints
    )

    total = time.perf_counter() - req_start
    print(f"[Perf] OpenAI LLM: {llm_dur:.4f} sec")
    print(f"[Perf] TOTAL REQUEST: {total:.4f} sec")
    print("==========================================\n")

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
