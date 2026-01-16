# chat_shared.py al deze functies hier woorden gedeelt gebruikt door main.py en chat.py

from typing import List, Tuple, Optional

# Database
from chat_engine.db import get_conn

# (optioneel, alleen als je ze gebruikt in de helpers)
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import random


def build_welcome_message(first_name: str | None) -> str:
    if first_name:
        return random.choice([
            f"Welkom {first_name}! Dit is een nieuwe chat voor vandaag. Wil je verder in een eerder gesprek? Open die dan via je geschiedenis.",
            f"Goed je weer te zien, {first_name} 😊 Vandaag starten we met een frisse chat.",
            f"Nieuwe dag, nieuwe chat {first_name} ✨ Je eerdere gesprekken blijven bewaard.",
            f"Hoi {first_name}! Dit gesprek is nieuw voor vandaag. Wil je verder waar je eerder was? Open dan een eerdere chat.",

        ])
    else:
        return random.choice([
            "Welkom! Dit is een nieuwe chat voor vandaag. Wil je verder in een eerder gesprek? Open die dan via je geschiedenis.",
            "Goed je weer te zien 😊 Vandaag starten we met een frisse chat.",
            "Nieuwe dag, nieuwe chat ✨ Je eerdere gesprekken blijven bewaard.",
            "Hoi! Dit gesprek is nieuw voor vandaag. Wil je verder waar je eerder was? Open dan een eerdere chat.",

        ])


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

def get_or_create_conversation(conn, owner_id: int, first_name: str | None = None):
    """
    Haalt de conversation van VANDAAG (Europe/Amsterdam) op,
    of maakt er één aan als die nog niet bestaat.
    """
    cur = conn.cursor()

    # 🗓️ 1) Bepaal vandaag (Europe/Amsterdam)
    today = datetime.now(ZoneInfo("Europe/Amsterdam")).date()

    # 🔍 2) Bestaat er al een conversation voor vandaag?
    cur.execute(
        """
        SELECT id
        FROM conversations
        WHERE user_id = %s
          AND conversation_date = %s
        LIMIT 1
        """,
        (owner_id, today),
    )
    row = cur.fetchone()
    if row:
        return row["id"] if isinstance(row, dict) else row[0]

    # ➕ 3) Nieuwe conversation aanmaken
    cur.execute(
        """
        INSERT INTO conversations (user_id, conversation_date, started_at)
        VALUES (%s, %s, NOW())
        RETURNING id
        """,
        (owner_id, today),
    )
    row = cur.fetchone()
    conversation_id = row["id"] if isinstance(row, dict) else row[0]

    # 👋 4) Welcome message toevoegen (system)
    welcome_text = build_welcome_message(first_name)
    cur.execute(
    """
    INSERT INTO messages (conversation_id, role, content)
    VALUES (%s, %s, %s)
    """,
    (conversation_id, "system", welcome_text),
    )


    conn.commit()
    return conversation_id


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

def get_conversation_history_grouped(conn, owner_id: int):
    """
    Geeft conversaties terug gegroepeerd per dag:
    - today
    - yesterday
    - older

    Gebaseerd op Europe/Amsterdam.
    """
    cur = conn.cursor()

    # 🗓️ Bepaal vandaag en gisteren (Amsterdam)
    today = datetime.now(ZoneInfo("Europe/Amsterdam")).date()
    yesterday = today - timedelta(days=1)

    # 🔍 Haal alle conversaties van deze user op
    cur.execute(
        """
        SELECT id, conversation_date
        FROM conversations
        WHERE user_id = %s
          AND conversation_date IS NOT NULL
        ORDER BY conversation_date DESC
        """,
        (owner_id,),
    )

    rows = cur.fetchall()

    history = {
        "today": [],
        "yesterday": [],
        "older": []
    }

    for row in rows:
        conv_id = row["id"] if isinstance(row, dict) else row[0]
        conv_date = row["conversation_date"] if isinstance(row, dict) else row[1]

        if conv_date == today:
            history["today"].append({
                "conversation_id": conv_id,
                "conversation_date": str(conv_date)
            })
        elif conv_date == yesterday:
            history["yesterday"].append({
                "conversation_id": conv_id,
                "conversation_date": str(conv_date)
            })
        else:
            history["older"].append({
                "conversation_id": conv_id,
                "conversation_date": str(conv_date)
            })

    return history

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
        SELECT role, content, created_at,
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
            "created_at": r["created_at"] if isinstance(r, dict) else r[2],
        }
        for r in rows
    ]

    return messages

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
    SELECT role, content, created_at
    FROM messages
    WHERE conversation_id = %s
    ORDER BY created_at DESC
    LIMIT %s
    """,
    (conv_id, limit),
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
        SELECT role, content,created_at,
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

