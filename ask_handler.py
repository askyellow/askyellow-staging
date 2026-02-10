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
import logging

logger = logging.getLogger(__name__)

router = APIRouter()
time_context = build_time_context()
logging.basicConfig(level=logging.INFO)

# =============================================================
# ASK ENDPOINT
# =============================================================
logger.warning("🔥 ASK_HANDLER VERSION XYZ LOADED 🔥")

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

        logger.info(
    "[ASK] incoming",
    extra={
        "session_id": session_id,
        "mode": mode,
        "intent": intent
    }
    )
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
    
    # =========================================================
    # 🔍 SEARCH FLOW
    # =========================================================

    if mode == "search":
        return {
            "answer": "Test affiliate render",
            "affiliate_results": [
                {
                    "title": "Robotstofzuiger Test A",
                    "price": 199,
                    "url": "https://example.com"
                },
                {
                    "title": "Robotstofzuiger Test B",
                    "price": 179,
                    "url": "https://example.com"
                }
            ]
        }

    # if mode == "search":

    #     logger.info(
    #         "[SEARCH] start",
    #         extra={
    #             "session_id": session_id,
    #             "question": question
    #         }
    #     )

    #     category = detect_category(question)
    #     specificity = detect_specificity(question)

    #     logger.info(
    #         "[SEARCH] analysis",
    #         extra={
    #             "session_id": session_id,
    #             "category": category,
    #             "specificity": specificity,
    #             "search_ready": search_ready
    #         }
    #     )

    #     affiliate_results = None

    #     # 🔹 NOG NIET GENOEG INFO → AI VRAAGT DOOR
    #     if specificity in ("low", "medium"):
    #         logger.info(
    #             "[SEARCH] followup",
    #             extra={
    #                 "session_id": session_id,
    #                 "reason": "insufficient_specificity"
    #             }
    #         )

    #         answer = ai_search_followup(
    #             user_input=question,
    #             search_query=question
    #         )

    #     # 🔹 GENOEG INFO → ZOEKEN
    #     elif specificity == "high":
    #         logger.info(
    #             "[SEARCH] executing searches",
    #             extra={
    #                 "session_id": session_id
    #             }
    #         )

    #         web_results = do_websearch(question)

    #         logger.info(
    #             "[SEARCH] websearch done",
    #             extra={
    #                 "session_id": session_id,
    #                 "web_result_count": len(web_results) if web_results else 0
    #             }
    #         )

    #         affiliate_results = await do_affiliate_search(
    #             search_query=question,
    #             session_id=session_id
    #         )

    #         logger.info(
    #             "[SEARCH] affiliate search done",
    #             extra={
    #                 "session_id": session_id,
    #                 "affiliate_result_count": len(affiliate_results)
    #                 if affiliate_results else 0
    #             }
    #         )

    #         answer = "Ik heb een aantal goede opties voor je gevonden 👇"

    #     # 🔹 SPECIFICITY HOOG MAAR SEARCH NOG NIET KLAAR
    #     # elif specificity == "high" and not search_ready:
    #     #     logger.info(
    #     #         "[SEARCH] followup",
    #     #         extra={
    #     #             "session_id": session_id,
    #     #             "reason": "search_not_ready"
    #     #         }
    #     #     )

    #         answer = ai_search_followup(
    #             user_input=question,
    #             search_query=question
    #         )

    #     store_message_pair(session_id, question, answer)

    #     payload = {
    #         "type_": "search",
    #         "answer": answer,
    #         "intent": intent,
    #         "mode": "search"
    #     }

    #     if affiliate_results:
    #         logger.info(
    #             "[SEARCH] attaching affiliate results to response",
    #             extra={
    #                 "session_id": session_id,
    #                 "affiliate_result_count": len(affiliate_results)
    #             }
    #         )
    #         payload["affiliate_results"] = affiliate_results

    #     else:
    #         logger.info(
    #             "[SEARCH] no affiliate results attached",
    #             extra={
    #                 "session_id": session_id
    #             }
    #         )

    #     logger.info(
    #         "[SEARCH] done",
    #         extra={
    #             "session_id": session_id,
    #             "has_affiliate_results": bool(affiliate_results)
    #         }
    #     )

    #     return _response(**payload)

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
        "type_": "text",
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
        "type_": type_,
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
