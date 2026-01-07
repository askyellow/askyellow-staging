from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from fastapi import APIRouter
from app.routes.auth import get_auth_user_from_session, get_or_create_user_for_auth

router = APIRouter()

import os

from app.db.models import (
    get_or_create_user,
    get_or_create_conversation,
)


from app.db.models import get_db_conn

from app.core.config import client



# =============================================================
# CHAT HISTORY – VOOR MODEL CONTEXT (BLOK 1) NIEUW!!!
# =============================================================

def get_history_for_model(conn, session_id, limit=30):
    """
    Haalt de LAATSTE berichten van een gesprek op,
    bedoeld voor LLM-context (oud → nieuw).
    """
    cur = conn.cursor()

    auth_user = get_auth_user_from_session(conn, session_id)
    owner_id = (
        get_or_create_user_for_auth(conn, auth_user["id"], session_id)
        if auth_user
        else get_or_create_user(conn, session_id)
    )

    conv_id = get_or_create_conversation(conn, owner_id)

    cur.execute(
        """
        SELECT role, content
        FROM messages
        WHERE conversation_id = %s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (conv_id, limit)
    )

    rows = cur.fetchall()
    rows.reverse()  # 🔥 cruciaal: oud → nieuw voor het model

    return conv_id, rows


@router.get("/chat")
def serve_chat_page():
    base = os.path.dirname(os.path.abspath(__file__))
    return FileResponse(os.path.join(base, "static/chat/chat.html"))

@router.get("/chat/history")
async def chat_history(session_id: str):
    conn = get_db_conn()
    cur = conn.cursor()

    auth_user = get_auth_user_from_session(conn, session_id)

    if auth_user:
        owner_id = get_or_create_user_for_auth(conn, auth_user["id"],)
    else:
        owner_id = get_or_create_user(conn, session_id)

    conv_id = get_or_create_conversation(conn, owner_id)

    cur.execute(
        """
        SELECT role, content
        FROM messages
        WHERE conversation_id = %s
        ORDER BY created_at ASC
        """,
        (conv_id,)
    )

    rows = cur.fetchall()
    conn.close()

    return {
        "messages": [
            {"role": r["role"], "content": r["content"]}
            for r in rows
        ]
    }

def get_conversation_history_for_model(conn, session_id, limit=12):
    cur = conn.cursor()

    auth_user = get_auth_user_from_session(conn, session_id)
    owner_id = (
        get_or_create_user_for_auth(conn, auth_user["id"], session_id)
        if auth_user
        else get_or_create_user(conn, session_id)
    )

    conv_id = get_or_create_conversation(conn, owner_id)

    cur.execute(
        """
        SELECT role, content
        FROM messages
        WHERE conversation_id = %s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (conv_id, limit)
    )

    rows = list(reversed(cur.fetchall()))
    return conv_id, rows



   
@router.post("/chat")
async def chat(payload: dict):
    session_id = payload.get("session_id")
    user_input = payload.get("message", "").strip()

    if not session_id or not user_input:
        raise HTTPException(
            status_code=400,
            detail="session_id of message ontbreekt"
        )

    conn = get_db_conn()
    cur = conn.cursor()

    # 1️⃣ History ophalen (Memory v1)
    conv_id, history = get_conversation_history_for_model(
        conn,
        session_id,
        limit=30
    )

    #print("=== HISTORY FROM DB ===")
    #for i, msg in enumerate(history):
    #    print(i, msg["role"], msg["content"][:80])
    #print("=======================")

    # 2️⃣ Payload voor model bouwen
    messages_for_model = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        }
    ]

    for msg in history:
        messages_for_model.append({
            "role": msg["role"],
            "content": msg["content"]
        })

    messages_for_model.append({
        "role": "user",
        "content": user_input
    })

    print("=== PAYLOAD TO MODEL ===")
    for i, msg in enumerate(messages_for_model):
        print(i, msg["role"], msg["content"][:80])
    print("========================")

    # 3️⃣ OpenAI call
    ai_response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages_for_model
    )

    assistant_reply = ai_response.choices[0].message.content

    # 4️⃣ Opslaan: user message
    cur.execute(
        """
        INSERT INTO messages (conversation_id, role, content)
        VALUES (%s, %s, %s)
        """,
        (conv_id, "user", user_input)
    )

    # 5️⃣ Opslaan: assistant reply
    cur.execute(
        """
        INSERT INTO messages (conversation_id, role, content)
        VALUES (%s, %s, %s)
        """,
        (conv_id, "assistant", assistant_reply)
    )

    conn.commit()
    conn.close()

    # 6️⃣ Terug naar frontend
    return {
        "reply": assistant_reply
    }
