from fastapi import APIRouter, Request, HTTPException, Depends, Query
from fastapi.responses import FileResponse
import os
#from core.time_context import build_time_context, greeting
from chat_engine.db import get_conn
from chat_shared import (
    get_active_conversation,
    create_new_conversation,
    get_history_for_model,
    store_message_pair,
)
from llm import call_yellowmind_llm


router = APIRouter()



# @router.get("/chat")
# def serve_chat_page():
#     base = os.path.dirname(os.path.abspath(__file__))
#     return FileResponse(os.path.join(base, "static/chat/chat.html"))

# @router.get("/chat/conversation")
# def chat_get_conversation(
#     conversation_id: int,
#     session_id: str = Query(...)
# ):
#     conn = get_conn()
#     try:
#         user = get_user_by_session(conn, session_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         cur = conn.cursor()

#         # 🔐 Check ownership
#         cur.execute(
#             """
#             SELECT id
#             FROM conversations
#             WHERE id = %s AND user_id = %s
#             """,
#             (conversation_id, user["id"]),
#         )

#         if not cur.fetchone():
#             raise HTTPException(status_code=403, detail="Forbidden")

#         # 📩 Haal berichten op
#         cur.execute(
#             """
#             SELECT role, content, created_at
#             FROM messages
#             WHERE conversation_id = %s
#             ORDER BY created_at ASC
#             """,
#             (conversation_id,),
#         )

#         rows = cur.fetchall() or []

#         messages = []
#         for row in rows:
#             if isinstance(row, dict):
#                 role = row["role"]
#                 content = row["content"]
#             else:
#                 role, content = row[0], row[1]

#             messages.append({
#                 "role": role,
#                 "content": content,
#             })

#         return {
#             "conversation_id": conversation_id,
#             "messages": messages,
#         }

#     finally:
#         conn.close()



# @router.get("/chat/history-list")
# def chat_history_list(session_id: str = Query(...)):
#     conn = get_conn()
#     try:
#         user = get_user_by_session(conn, session_id)
#         if not user:
#             raise HTTPException(status_code=404, detail="User not found")

#         history = get_conversation_history_grouped(conn, user["id"])
#         return history

#     finally:
#         conn.close()

# nieuwe route ipv onderstaande
@router.get("/chat/history")
def chat_history(session_id: str):
    conn = get_conn()
    try:
        _, history = get_history_for_model(conn, session_id)
        return {
            "messages": [
                {"role": r["role"], "content": r["content"]}
                for r in history
            ]
        }
    finally:
        conn.close()


# @router.get("/chat/history")
# async def chat_history(session_id: str):
#     conn = get_conn()
#     cur = conn.cursor()

#     auth_user = get_auth_user_from_session(conn, session_id)

#     if auth_user:
#         owner_id = get_or_create_user_for_auth(conn, auth_user["id"], session_id)
#     else:
#         owner_id = get_or_create_user(conn, session_id)

#     # ❗ READ-ONLY: GEEN create
#     conv_id = get_today_conversation_id(conn, owner_id)

#     if not conv_id:
#         conn.close()
#         return {"messages": []}

#     cur.execute(
#         """
#         SELECT role, content
#         FROM messages
#         WHERE conversation_id = %s
#         ORDER BY created_at ASC
#         """,
#         (conv_id,),
#     )

#     rows = cur.fetchall()
#     conn.close()

#     return {
#         "messages": [
#             {"role": r["role"], "content": r["content"]}
#             for r in rows
#         ]
#     }

# nieuwe route ipv hier onderstaande 

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



# @router.post("/chat")
# def chat(payload: dict):
#     session_id = payload.get("session_id")
#     message = payload.get("message", "").strip()

#     if not session_id or not message:
#         raise HTTPException(status_code=400, detail="session_id of message ontbreekt")

#     # 1️⃣ History ophalen (read-only)
#     conn = get_conn()
#     _, history = get_history_for_model(conn, session_id)
#     conn.close()

#     # ⏰ Time context (centrale waarheid)
#     time_context = build_time_context()
#     hello = greeting()

#     # 2️⃣ Payload voor model bouwen
#     messages_for_model = [
#     {
#         "role": "system",
#         "content": f"""
#         {SYSTEM_PROMPT}

# {time_context}

# Begroeting voor dit gesprek: "{hello}"
# Gebruik deze begroeting exact zoals opgegeven.
# """
#     }
# ]
#     for msg in history:
#         messages_for_model.append({
#             "role": msg["role"],
#             "content": msg["content"]
#         })

#     messages_for_model.append({
#         "role": "user",
#         "content": user_input
#     })

#     # absolute noodrem
#     messages_for_model = messages_for_model[:20]


#     # 3️⃣ OpenAI call
#     ai_response = client.chat.completions.create(
#         model="gpt-4.1-mini",
#         messages=messages_for_model,
#         max_tokens=500
#     )

#     answer = extract_text_from_response(ai_response)

#     if not answer:
#         answer = "⚠️ Ik kreeg geen inhoudelijk antwoord terug, maar de chat werkt wel 🙂"

#     # 4️⃣ Opslaan: user message
#     cur.execute(
#         """
#         INSERT INTO messages (conversation_id, role, content)
#         VALUES (%s, %s, %s)
#         """,
#         (conv_id, "user", user_input)
#     )

#     # 5️⃣ Opslaan: assistant reply
#     cur.execute(
#         """
#         INSERT INTO messages (conversation_id, role, content)
#         VALUES (%s, %s, %s)
#         """,
#         (conv_id, "assistant", answer)
#     )

#     conn.commit()
#     conn.close()

#     # 6️⃣ Terug naar frontend
#     return {
#         "reply": answer
#     }

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

