from fastapi import APIRouter, Request, HTTPException

from db import get_db_conn
from chat_shared import get_auth_user_from_session, store_message_pair
from intent import detect_intent
from core.time_context import build_time_context

from category import detect_category
from specificity import detect_specificity
from search_questions import get_search_questions
from search_followup import interpret_search_followup

from websearch import do_websearch
from affiliate_search import do_affiliate_search
from llm import call_yellowmind_llm

router = APIRouter()
time_context = build_time_context()

# =============================================================
# ASK ENDPOINT
# =============================================================

@router.post("/ask")
async def ask(request: Request):
    payload = await request.json()

    # ---------------------------------------------------------
    # BASIC INPUT
    # ---------------------------------------------------------
    question = (payload.get("question") or "").strip()
    session_id = payload.get("session_id")
    language = payload.get("language", "nl")
    mode = payload.get("mode")  # frontend mag dit sturen
    search_ready = payload.get("search_ready", False)

    if not question:
        raise HTTPException(status_code=400, detail="Missing question")

    # ---------------------------------------------------------
    # AUTH (chat-only relevant, maar licht genoeg om altijd te doen)
    # ---------------------------------------------------------
    conn = get_db_conn()
    user = get_auth_user_from_session(conn, session_id)
    conn.close()

    # ---------------------------------------------------------
    # INTENT / MODE ROUTING
    # ---------------------------------------------------------
    intent = detect_intent(question)

    if not mode:
        mode = "search" if intent == "product" else "chat"

    # ---------------------------------------------------------
    # TIME SHORTCUT (globaal, los van search/chat)
    # ---------------------------------------------------------
    if _is_time_question(question):
        answer = f"Vandaag is het {time_context.today_string()}."
        store_message_pair(session_id, question, answer)
        return _response(
            type_="text",
            answer=answer,
            intent=intent,
            mode=mode
        )

    # =========================================================
    # 🔍 SEARCH FLOW
    # =========================================================

    if mode == "search":

        category = detect_category(question)
        specificity = detect_specificity(question)

        # 🔹 NOG NIET GENOEG INFO → AI VRAAGT DOOR
        if specificity in ("low", "medium"):
            answer = ai_search_followup(
                user_input=question,
                search_query=question  # ⚠️ dit is al de samengestelde query uit frontend
            )

        # 🔹 GENOEG INFO → ZOEKEN
        elif specificity == "high" and search_ready:
            web_results = do_websearch(question)
            affiliate_results = await do_affiliate_search(question)
            answer = "Ik heb een aantal goede opties voor je gevonden 👇"

        elif specificity == "high" and not search_ready:
            answer = ai_search_followup(
                user_input=question,
                search_query=question
            )
 
        store_message_pair(session_id, question, answer)

        payload = {
            "type": "search",
            "answer": answer,
            "intent": intent,
            "mode": "search",
        }

        if specificity == "high" and search_ready:
            payload["affiliate_results"] = affiliate_results

        return _response(**payload)

    # =========================================================
    # 💬 CHAT FALLBACK (ONGEWIIJZIGD)
    # =========================================================
    conn = get_db_conn()
    _, history = get_history_for_model(conn, session_id)
    conn.close()

    from search.web_context import build_web_context
    from websearch import do_websearch as run_websearch_internal
    from yellowmind import call_yellowmind_llm

    web_results = run_websearch_internal(question)
    web_context = build_web_context(web_results)

    hints = {
        "time_context": time_context,
        "web_context": web_context
    }

    if user and user.get("first_name"):
        hints["user_name"] = user["first_name"]

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


# =============================================================
# HELPERS
# =============================================================

def _is_time_question(question: str) -> bool:
    TIME_KEYWORDS = [
        "vandaag",
        "welke dag is het",
        "wat voor dag is het",
        "laatste jaarwisseling",
        "afgelopen jaarwisseling",
    ]
    q = question.lower()
    return any(k in q for k in TIME_KEYWORDS)


def _response(type_, answer, intent=None, mode=None, meta=None):
    response = {
        "type": type_,
        "answer": answer,
        "intent": intent,
        "mode": mode,
    }

    if meta:
        response["meta"] = meta

    return response


def detect_category(query: str) -> str:
    q = query.lower()

    if any(w in q for w in ["kopen", "prijs", "goedkoop", "beste"]):
        return "product"

    if any(w in q for w in ["hoe", "wat is", "uitleg"]):
        return "info"

    return "general"

def detect_specificity(query: str) -> str:
    length = len(query.split())

    if length <= 2:
        return "low"
    if length <= 5:
        return "medium"
    return "high"

def ai_search_followup(user_input: str, search_query: str) -> str:
    prompt = f"""
Je bent YellowMind, een behulpzame maar nuchtere zoekassistent.

Dit is een vervolgstap in dezelfde productzoektocht.
De gebruiker bouwt zijn zoekvraag stap voor stap op.

Huidige zoekcontext (samengevat):
"{search_query}"

Laatste antwoord van de gebruiker:
"{user_input}"

Je taak:
- Stel EXACT 1 korte, natuurlijke vervolgvraag
- Ga logisch verder op basis van de zoekcontext
- Gebruik wat de gebruiker al heeft aangegeven (zoals budget, gebruik, voorkeuren)
- Vraag NIET opnieuw naar iets dat al duidelijk is
- Geen lijstjes
- Geen uitleg
- Geen begroeting of afsluiting

Geef alleen de vervolgvraag.
""".strip()

    answer, _ = call_yellowmind_llm(
        question=prompt,
        language="nl",
        kb_answer=None,
        sql_match=None,
        history=[],
        hints={"mode": "search_followup"},
    )

    return (answer or "").strip()
