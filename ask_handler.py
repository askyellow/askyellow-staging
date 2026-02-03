from fastapi import APIRouter, Request, HTTPException

router = APIRouter()

# =============================================================
# MAIN ASK ENDPOINT
# =============================================================


@router.post("/ask")
async def ask(request: Request):
    payload = await request.json()

    question = payload.get("question")
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