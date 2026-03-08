import base64

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from chat_engine.db import get_conn

from chat_shared import (
    get_active_conversation,
    get_history_for_model,
    store_message_pair,
    get_user_history,
    get_or_create_daily_conversation,
    get_auth_user_from_session,
    build_welcome_message,
    get_history_for_llm,
)

from image_shared import (
    generate_image,
    analyze_uploaded_image,
    edit_uploaded_image,
    detect_uploaded_image_operation,
    read_and_validate_upload,
)

from llm import call_yellowmind_llm

router = APIRouter()


@router.get("/chat/history")
def chat_history(session_id: str):
    conn = get_conn()
    welcome_message = None

    user = get_auth_user_from_session(conn, session_id)

    if user:
        user_id = user["id"]

        active_conversation_id = get_or_create_daily_conversation(conn, user_id)

        today_history = get_user_history(conn, user_id, day="today")
        yesterday_history = get_user_history(conn, user_id, day="yesterday")

        if not today_history:
            welcome_message = build_welcome_message(user.get("first_name"))

    else:
        active_conversation_id = get_active_conversation(conn, session_id)
        _, today_history = get_history_for_model(conn, session_id, day="today")
        _, yesterday_history = get_history_for_model(conn, session_id, day="yesterday")
        welcome_message = build_welcome_message(None)

    conn.close()

    return {
        "active_conversation_id": active_conversation_id,
        "today": today_history,
        "yesterday": yesterday_history,
        "welcome": welcome_message,
    }


@router.post("/chat")
def chat(payload: dict):
    session_id = payload.get("session_id")
    message = payload.get("message", "").strip()
    wants_image = payload.get("wants_image", False)

    if not session_id or not message:
        raise HTTPException(status_code=400, detail="session_id of message ontbreekt")

    conn = get_conn()
    history = get_history_for_llm(conn, session_id)
    conn.close()

    hints = {}

    if wants_image:
        image_url = generate_image(message)

        if not image_url:
            raise HTTPException(status_code=500, detail="Afbeelding genereren mislukt")

        store_message_pair(session_id, message, "[IMAGE]" + image_url)

        return {
            "type": "image",
            "url": image_url
        }

    answer, _ = call_yellowmind_llm(
        question=message,
        language="nl",
        kb_answer=None,
        sql_match=None,
        hints=hints,
        history=history
    )

    if not answer:
        answer = "⚠️ Ik kreeg geen inhoudelijk antwoord terug."

    store_message_pair(session_id, message, answer)

    return {"reply": answer}


@router.post("/chat/image")
async def chat_with_uploaded_image(
    session_id: str = Form(...),
    message: str = Form(""),
    file: UploadFile = File(...),
):
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id ontbreekt")

    image_bytes, mime_type = await read_and_validate_upload(file)

    # ✅ originele upload opslaan als renderbare data-url in chat history
    original_image_data_url = (
        f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('utf-8')}"
    )
    user_log_text = f"[USER_IMAGE]{original_image_data_url}"

    conn = get_conn()
    history = get_history_for_llm(conn, session_id)
    conn.close()

    operation = detect_uploaded_image_operation(message)

    if operation == "edit":
        prompt = (message or "").strip()
        if not prompt:
            prompt = "Maak van deze afbeelding een nette karikatuur."

        image_src = edit_uploaded_image(
            image_bytes=image_bytes,
            mime_type=mime_type,
            prompt=prompt,
        )

        store_message_pair(session_id, user_log_text, f"[IMAGE]{image_src}")

        return {
            "type": "image",
            "mode": "edit",
            "url": image_src,
            "reply": "Hier is je bewerkte afbeelding."
        }

    answer = analyze_uploaded_image(
        image_bytes=image_bytes,
        mime_type=mime_type,
        question=message,
        history=history,
    )

    store_message_pair(session_id, user_log_text, answer)

    return {
        "type": "vision",
        "mode": "analyze",
        "reply": answer,
    }

@router.post("/chat/reset")
def reset_chat(payload: dict):
    session_id = payload.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400)

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE conversations
            SET ended_at = NOW()
            WHERE session_id = %s
              AND ended_at IS NULL
            """,
            (session_id,)
        )
        conn.commit()
    finally:
        conn.close()

    return {"ok": True}