from fastapi import APIRouter, Request, HTTPException

from db import get_db_conn
from chat_shared import get_auth_user_from_session
from intent import detect_intent
from core.time_context import build_time_context
from chat_shared import store_message_pair
from category import detect_category

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
    # PLACEHOLDERS (tijdelijk)
    # -----------------------------
    if mode == "search":
        answer = "Ik kan je helpen kiezen. Kun je iets meer vertellen over wat je zoekt?"
    else:
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
