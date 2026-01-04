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

def get_recent_messages(session_id: str, limit: int = 10):
    conn = get_db_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT role, content
        FROM chat_messages
        WHERE session_id = %s
        ORDER BY created_at DESC
        LIMIT %s
    """, (session_id, limit))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [
        {"role": role, "content": content}
        for role, content in reversed(rows)
    ]
