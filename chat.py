from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import FileResponse
import os
from core.time_context import build_time_context, greeting
from chat_engine.db import get_conn
from chat_engine.utils import get_logical_date


router = APIRouter()

def get_auth_user_from_session(conn, session_id: str):
    cur = conn.cursor()
    cur.execute("""
        SELECT au.id, au.first_name
        FROM user_sessions us
        JOIN auth_users au ON au.id = us.user_id
        WHERE us.session_id = %s
          AND us.expires_at > NOW()
    """, (session_id,))

    row = cur.fetchone()
    if not row:
        return None

    return {
    "id": row["id"],
    "first_name": row["first_name"]
}

def get_or_create_user_for_auth(conn, auth_user_id: int, session_id: str):
    """
    Zorgt dat een ingelogde user altijd dezelfde 'users'-row krijgt,
    gebaseerd op een stabiele session_id: auth-<auth_user_id>.
    """
    cur = conn.cursor()
    stable_sid = f"auth-{auth_user_id}"

    # 1) Bestaat deze user al?
    cur.execute("SELECT id FROM users WHERE session_id = %s", (stable_sid,))
    row = cur.fetchone()
    if row:
        # RealDictCursor -> dict; anders tuple
        return row["id"] if isinstance(row, dict) else row[0]

    # 2) Anders aanmaken
    cur.execute(
        """
        INSERT INTO users (session_id)
        VALUES (%s)
        RETURNING id
        """,
        (stable_sid,),
    )
    row = cur.fetchone()
    conn.commit()

    return row["id"] if isinstance(row, dict) else row[0]

def get_or_create_conversation(conn, owner_id: int):
    """
    Haalt de meest recente conversation van deze user op,
    of maakt er één aan als die nog niet bestaat.
    """
    cur = conn.cursor()

    # 1) Bestaat er al een conversation?
    cur.execute(
        """
        SELECT id
        FROM conversations
        WHERE user_id = %s
        ORDER BY started_at DESC
        LIMIT 1
        """,
        (owner_id,),
    )
    row = cur.fetchone()
    if row:
        return row["id"] if isinstance(row, dict) else row[0]

    # 2) Anders: nieuwe conversation aanmaken
    cur.execute(
        """
        INSERT INTO conversations (user_id)
        VALUES (%s)
        RETURNING id
        """,
        (owner_id,),
    )
    row = cur.fetchone()
    conn.commit()

    return row["id"] if isinstance(row, dict) else row[0]

def get_or_create_user(conn, session_id: str) -> int:
    """Zoek user op session_id, maak anders een nieuwe aan."""
    cur = conn.cursor()

    cur.execute(
        "SELECT id FROM users WHERE session_id = %s",
        (session_id,),
    )
    row = cur.fetchone()
    if row:
        return row["id"] if isinstance(row, dict) else row[0]

    cur.execute(
        """
        INSERT INTO users (session_id)
        VALUES (%s)
        RETURNING id
        """,
        (session_id,),
    )
    row = cur.fetchone()
    conn.commit()

    return row["id"] if isinstance(row, dict) else row[0]

def save_message(conn, conversation_id: int, role: str, content: str):
    cur = conn.cursor()

    # Message opslaan
    cur.execute(
        """
        INSERT INTO messages (conversation_id, role, content)
        VALUES (%s, %s, %s)
        """,
        (conversation_id, role, content),
    )

    # Conversation bijwerken
    cur.execute(
        """
        UPDATE conversations
        SET last_message_at = NOW()
        WHERE id = %s
        """,
        (conversation_id,),
    )

    conn.commit()

def get_recent_messages(conn, conversation_id: int, limit: int = 12):
    """
    Haal de laatste berichten van een gesprek op
    (oud → nieuw), voor model-context.
    """
    cur = conn.cursor()

    cur.execute(
        """
        SELECT role, content
        FROM messages
        WHERE conversation_id = %s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (conversation_id, limit),
    )

    rows = cur.fetchall()

    # Oud → nieuw volgorde
    rows = list(reversed(rows))

    # Normalize output (dict vs tuple)
    messages = [
        {
            "role": r["role"] if isinstance(r, dict) else r[0],
            "content": r["content"] if isinstance(r, dict) else r[1],
        }
        for r in rows
    ]

    return messages


@router.get("/chat")
def serve_chat_page():
    base = os.path.dirname(os.path.abspath(__file__))
    return FileResponse(os.path.join(base, "static/chat/chat.html"))


@router.get("/chat/history")
async def chat_history(session_id: str):
    conn = get_conn()
    cur = conn.cursor()

    auth_user = get_auth_user_from_session(conn, session_id)

    if auth_user:
        owner_id = get_or_create_user_for_auth(conn, auth_user["id"], session_id)
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

@router.post("/chat")
async def chat(payload: dict):
    session_id = payload.get("session_id")
    user_input = payload.get("message", "").strip()

    if not session_id or not user_input:
        raise HTTPException(
            status_code=400,
            detail="session_id of message ontbreekt"
        )

    conn = get_conn()
    cur = conn.cursor()

    # 1️⃣ History ophalen
    conv_id, history = get_conversation_history_for_model(
        conn,
        session_id,
        limit=30
    )

    # ⏰ Time context (centrale waarheid)
    time_context = build_time_context()
    hello = greeting()

    # 2️⃣ Payload voor model bouwen
    messages_for_model = [
    {
        "role": "system",
        "content": f"""
        {SYSTEM_PROMPT}

{time_context}

Begroeting voor dit gesprek: "{hello}"
Gebruik deze begroeting exact zoals opgegeven.
"""
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

    # absolute noodrem
    messages_for_model = messages_for_model[:20]


    # 3️⃣ OpenAI call
    ai_response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages_for_model,
        max_tokens=500
    )

    answer = extract_text_from_response(ai_response)

    if not answer:
        answer = "⚠️ Ik kreeg geen inhoudelijk antwoord terug, maar de chat werkt wel 🙂"

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
        (conv_id, "assistant", answer)
    )

    conn.commit()
    conn.close()

    # 6️⃣ Terug naar frontend
    return {
        "reply": answer
    }

    
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

def store_message_pair(session_id, user_text, assistant_text):
    try:
        conn = get_conn()
        conv_id, _ = get_history_for_model(conn, session_id)
        save_message(conn, conv_id, "user", user_text)
        save_message(conn, conv_id, "assistant", assistant_text)
        conn.commit()
        conn.close()
    except Exception as e:
        print("⚠️ History save failed:", e)
