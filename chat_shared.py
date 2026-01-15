# chat_shared.py

from typing import List, Tuple, Optional

# Database
from chat_engine.db import get_conn

# (optioneel, alleen als je ze gebruikt in de helpers)
from datetime import datetime

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
