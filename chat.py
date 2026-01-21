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
)
from llm import call_yellowmind_llm


router = APIRouter()

@router.get("/chat/history")
def chat_history(session_id: str, day: str | None = None):
    conn = get_conn()
    try:
        user = get_auth_user_from_session(conn, session_id)

        if user:
            rows = get_user_history(conn, user["id"], day)
        else:
            _, rows = get_history_for_model(conn, session_id, day)

        return {
            "messages": [
                {
                    "role": r["role"],
                    "content": r["content"],
                    "created_at": r["created_at"]
                }
                for r in rows
            ]
        }
    finally:
        conn.close()


@router.post("/chat")
def chat(payload: dict):
    session_id = payload.get("session_id")
    message = payload.get("message", "").strip()

    if not session_id or not message:
        raise HTTPException(status_code=400, detail="session_id of message ontbreekt")

    # 1️⃣ History ophalen (read-only)
    conn = get_conn()
    _, history = get_history_for_model(conn, session_id)
    conn.close()

    # 2️⃣ Hints (nu leeg, later uitbreidbaar)
    hints = {}

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

