# chat_shared.py al deze functies hier woorden gedeelt gebruikt door main.py en chat.py

from typing import List, Tuple, Optional

# Database
from chat_engine.db import get_conn

# (optioneel, alleen als je ze gebruikt in de helpers)
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from core.time_context import get_logical_date

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

# leest huidge converstatie READ ONLY
def get_active_conversation(conn, session_id: str):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id
        FROM conversations
        WHERE session_id = %s
          AND ended_at IS NULL
        ORDER BY started_at DESC
        LIMIT 1
        """,
        (session_id,)
    )
    row = cur.fetchone()
    return row["id"] if row else None


# maakt nieuwe coverstatie WRITE ONLY
def create_new_conversation(conn, session_id: str) -> int:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO conversations (session_id, started_at)
        VALUES (%s, NOW())
        RETURNING id
        """,
        (session_id,)
    )
    conv_id = cur.fetchone()["id"]
    conn.commit()
    return conv_id

#Haalt history op voor ingelogde users op basis van conversation_date.

def get_user_history(conn, user_id: int, day: str | None = None, limit=50):
    """
    Haalt history op voor ingelogde users op basis van conversation_date.
    day = None | 'today' | 'yesterday'
    """
    cur = conn.cursor()

    today = get_logical_date()  # ✅ Europe/Amsterdam leidend

    if day == "today":
        date_filter = "conversation_date = %s"
        params = [user_id, today]

    elif day == "yesterday":
        date_filter = "conversation_date = %s"
        params = [user_id, today - timedelta(days=1)]

    else:
        date_filter = "1=1"
        params = [user_id]

    cur.execute(
        f"""
        SELECT c.id AS conversation_id,
               m.role,
               m.content,
               m.created_at
        FROM conversations c
        JOIN messages m ON m.conversation_id = c.id
        WHERE c.user_id = %s
          AND {date_filter}
        ORDER BY m.created_at ASC
        LIMIT %s
        """,
        (*params, limit)
    )

    return cur.fetchall()

# aanmaken of ophalen dagelijkse converstatie
def get_or_create_daily_conversation(conn, user_id: int) -> int:
    """
    Zorgt dat een user exact 1 conversation per dag heeft.
    """
    today = get_logical_date()

    cur = conn.cursor()

    # 1. Bestaat er al een conversation voor deze user + vandaag?
    cur.execute(
        """
        SELECT id
        FROM conversations
        WHERE user_id = %s
          AND conversation_date = %s
          AND ended_at IS NULL
        LIMIT 1
        """,
        (user_id, today)
    )

    row = cur.fetchone()
    if row:
        return row["id"]

    # 2. Zo niet → nieuwe conversation maken
    cur.execute(
        """
        INSERT INTO conversations (
            user_id,
            conversation_date,
            started_at,
            last_message_at
        )
        VALUES (%s, %s, NOW(), NOW())
        RETURNING id
        """,
        (user_id, today)
    )

    conv_id = cur.fetchone()["id"]
    conn.commit()
    return conv_id

# haalt bestaande history op READ ONLY    

def get_history_for_model(conn, session_id: str, day: str | None = None, limit=30):
    # 🔑 ALLEEN guest-flow
    conv_id = get_active_conversation(conn, session_id)
    if not conv_id:
        return None, []

    cur = conn.cursor()

    params = [conv_id]
    date_filter = ""

    if day == "today":
        start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        date_filter = "AND created_at >= %s"
        params.append(start)

    elif day == "yesterday":
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        yesterday_start = today_start - timedelta(days=1)
        date_filter = "AND created_at >= %s AND created_at < %s"
        params.extend([yesterday_start, today_start])

    params.append(limit)

    cur.execute(
        f"""
        SELECT role, content, created_at
        FROM messages
        WHERE conversation_id = %s
        {date_filter}
        ORDER BY created_at ASC
        LIMIT %s
        """,
        tuple(params)
    )

    return conv_id, cur.fetchall()



   
# slaat alles op de in DB
def store_message_pair(session_id, user_text, assistant_text):
    conn = get_conn()
    try:
        user = get_auth_user_from_session(conn, session_id)

        if user:
            conv_id = get_or_create_daily_conversation(conn, user["id"])
        else:
            # guest → oud gedrag
            conv_id = get_active_conversation(conn, session_id)
            if not conv_id:
                conv_id = create_new_conversation(conn, session_id)

        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO messages (conversation_id, role, content)
            VALUES (%s, %s, %s)
            """,
            (conv_id, "user", user_text)
        )

        cur.execute(
            """
            INSERT INTO messages (conversation_id, role, content)
            VALUES (%s, %s, %s)
            """,
            (conv_id, "assistant", assistant_text)
        )

        # last_message_at bijwerken
        cur.execute(
            """
            UPDATE conversations
            SET last_message_at = NOW()
            WHERE id = %s
            """,
            (conv_id,)
        )

        conn.commit()
    finally:
        conn.close()

    # deze functie haalt op voor de gespreksconversatie (Yello terug lezen)   

def get_history_for_llm(conn, session_id: str, limit=30):
    user = get_auth_user_from_session(conn, session_id)
    cur = conn.cursor()

    if user:
        # 1️⃣ haal actieve conversation voor deze user
        cur.execute("""
            SELECT id
            FROM conversations
            WHERE user_id = %s
            AND ended_at IS NULL
            ORDER BY started_at DESC
            LIMIT 1
        """, (user["id"],))
        row = cur.fetchone()
        if not row:
            return []

        conv_id = row["id"]
    else:
        # guest
        conv_id = get_active_conversation(conn, session_id)
        if not conv_id:
            return []

    # 2️⃣ haal ALLE messages uit die conversation
    cur.execute("""
        SELECT role, content
        FROM messages
        WHERE conversation_id = %s
        ORDER BY created_at ASC
        LIMIT %s
    """, (conv_id, limit))

    rows = cur.fetchall()

    # 3️⃣ normaliseer voor LLM
    return [
        {"role": r["role"], "content": r["content"]}
        for r in rows
        if isinstance(r["content"], str)
    ]

