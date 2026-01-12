# app/db/models.py

import os
import psycopg2
import psycopg2.extras

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is niet ingesteld")
    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor
    )

def init_db():
    conn = get_db_conn()
    cur = conn.cursor()

    # users
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            session_id TEXT UNIQUE NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    # conversations
    cur.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_message_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            title TEXT
        );
    """)

    # messages
    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    conn.commit()
    conn.close()
def get_or_create_user(conn, session_id: str) -> int:
    """Zoek user op session_id, maak anders een nieuwe aan."""
    cur = conn.cursor()

    cur.execute(
        "SELECT id FROM users WHERE session_id = %s",
        (session_id,)
    )
    row = cur.fetchone()
    if row:
        return row["id"]

    cur.execute(
        "INSERT INTO users (session_id) VALUES (%s) RETURNING id",
        (session_id,),
    )
    conn.commit()
    return cur.fetchone()["id"]


def get_or_create_conversation(conn, user_id: int) -> int:
    cur = conn.cursor()

    # 🔥 Pak de MEEST RECENTE conversation
    cur.execute(
        """
        SELECT id
        FROM conversations
        WHERE user_id = %s
        ORDER BY last_message_at DESC
        LIMIT 1
        """,
        (user_id,)
    )
    row = cur.fetchone()
    if row:
        return row[0]

    # ❗ Alleen als er echt GEEN bestaat → nieuwe maken
    cur.execute(
        """
        INSERT INTO conversations (user_id, started_at, last_message_at)
        VALUES (%s, NOW(), NOW())
        RETURNING id
        """,
        (user_id,)
    )
    conn.commit()
    return cur.fetchone()[0]



def save_message(conn, conversation_id: int, role: str, content: str):
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO messages (conversation_id, role, content)
        VALUES (%s, %s, %s)
        """,
        (conversation_id, role, content),
    )

    cur.execute(
    """
    UPDATE conversations
    SET last_message_at = NOW()
    WHERE id = %s
    """,
    (conv_id,)
)


    conn.commit()
