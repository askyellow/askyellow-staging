from app.db.connection import get_db_conn

def init_db():
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id SERIAL PRIMARY KEY,
            session_id TEXT,
            role TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


def save_message(session_id: str, role: str, content: str) -> None:
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO chat_messages (session_id, role, content)
            VALUES (%s, %s, %s)
            """,
            (session_id, role, content),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()


def get_recent_messages(session_id: str, limit: int = 10) -> list[dict]:
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT role, content
            FROM chat_messages
            WHERE session_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (session_id, limit),
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    # oldest → newest (handig voor LLM history)
    rows.reverse()
    return [{"role": r, "content": c} for (r, c) in rows]
