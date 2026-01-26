from fastapi import APIRouter, Request, HTTPException, Depends, Query
from fastapi.responses import FileResponse
from datetime import datetime, timedelta, timezone

import os
#from core.time_context import build_time_context, greeting
from chat_engine.db import get_conn
from chat_shared import (
    get_active_conversation,
    create_new_conversation,
    get_history_for_model,
    store_message_pair,
    get_user_history,
    get_or_create_daily_conversation,
    get_history_for_model,
    get_auth_user_from_session,
    build_welcome_message,
    get_history_for_llm,
)
from image_shared import (
    wants_image,
    generate_image,
    detect_intent,
    require_auth_session,
    handle_image_intent,
    )
from llm import call_yellowmind_llm


router = APIRouter()

# /chat/history endpoint (voorbeeldstructuur)
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

    # 1️⃣ history ophalen
    conn = get_conn()
    history = get_history_for_llm(conn, session_id)
    conn.close()

    hints = {}

    # 🔥 2️⃣ IMAGE FLOW
    if wants_image:
        image_url = generate_image(message)  # jouw image-functie

        # opslag (optioneel)
        store_message_pair(session_id, message, "[IMAGE]" + image_url)

        return {
            "type": "image",
            "url": image_url
        }

    # 3️⃣ LLM call
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

    # 4️⃣ Opslaan (create gebeurt hier)
    store_message_pair(session_id, message, answer)

    return {"reply": answer}

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

