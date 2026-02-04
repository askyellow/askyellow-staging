from fastapi import APIRouter, Request, HTTPException

from db import get_db_conn
from chat_shared import get_auth_user_from_session
from intent import detect_intent
from core.time_context import build_time_context
from chat_shared import store_message_pair
from category import detect_category
from specificity import detect_specificity
from search_questions import get_search_questions
from search_followup import interpret_search_followup


router = APIRouter()
time_context = build_time_context()

# =============================================================
# ASK ENDPOINT
# =============================================================

@router.post("/ask")
async def ask(request: Request):
    payload = await request.json()

    question = (payload.get("question") or "").strip()
    session_id = payload.get("session_id")
    language = payload.get("language", "nl")

    if not question:
        raise HTTPException(status_code=400, detail="Missing question")

    # -----------------------------
    # AUTH
    # -----------------------------
    conn = get_db_conn()
    user = get_auth_user_from_session(conn, session_id)
    conn.close()

    # -----------------------------
    # INTENT
    # -----------------------------
    intent = detect_intent(question)
    mode = "search" if intent == "product" else "chat"

    intent = detect_intent(question)
    category = detect_category(question)
    specificity = detect_specificity(question)

    # -----------------------------
    # TIME SHORTCUT
    # -----------------------------
    if _is_time_question(question):
        answer = f"Vandaag is het {TIME_CONTEXT.today_string()}."
        store_message_pair(session_id, question, answer)
        return _response(
            type_="text",
            answer=answer,
            intent=intent
        )

    # -----------------------------
    # MODE SELECT (voorbereid)
    # -----------------------------
    mode = payload.get("mode")
    if not mode:
        mode = "search" if intent == "product" else "chat"

    # -----------------------------
    # SEARCH modules AI
    # -----------------------------
    if mode == "search" and specificity == "low":
        questions = get_search_questions(category)
        answer = " ".join(questions[:2])

        store_message_pair(session_id, question, answer)

        return _response(
            type_="search",
            answer=answer,
            intent=intent,
            mode=mode
        )
        
    if mode == "search" and specificity == "high":
        answer = (
        "Ik heb alvast een aantal opties voor je geselecteerd. "
        "Is dit voldoende, of zal ik verder voor je zoeken?"
    )        
        store_message_pair(session_id, question, answer)
        return _response(
                    type_="search",
                    answer=answer,
                    intent=intent,
                    mode=mode
                )
    
    # ----------------------------------
    # FOLLOW-UP OP VERKOPERSVRAAG
    # ----------------------------------
    if mode == "search" and specificity == "high":
        followup = interpret_search_followup(question)

        if followup == "accept":
            answer = "Top! Dan laat ik deze opties voor je staan 👍"
            store_message_pair(session_id, question, answer)
            return _response(
                type_="search",
                answer=answer,
                intent=intent,
                mode=mode
            )

        if followup == "refine":
            answer = "Helder 🙂 Waar zal ik extra op letten bij het verder zoeken?"
            store_message_pair(session_id, question, answer)
            return _response(
                type_="search",
                answer=answer,
                intent=intent,
                mode=mode
            )

    # ----------------------------------
    # SEARCH fallback: product zonder categorie
    # ----------------------------------
    if mode == "search" and category is None:
        answer = (
            "Ik kan je helpen bij het kiezen 😊 "
            "Kun je aangeven waar je het product voor wilt gebruiken "
            "of waar je op wilt letten?"
        )

        store_message_pair(session_id, question, answer)

        return _response(
            type_="search",
            answer=answer,
            intent=intent,
            mode=mode
        )
    # ----------------------------------
    # SEARCH algemene fallback
    # ----------------------------------
    answer = "Ik help je zo goed mogelijk verder 😊"
    store_message_pair(session_id, question, answer)
    return _response(
    type_="text",
    answer=answer,
    intent=intent,
    mode=mode
)   

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


def _response(type_: str, answer: str, intent: str, mode: str | None = None):
    return {
        "type": type_,
        "answer": answer,
        "meta": {
            "intent": intent,
            "mode": mode
        }
    }
