from app.db.connection import get_db_conn
from app.db.queries import (
    get_recent_messages,
    save_message,
)

def load_history_for_llm(session_id: str) -> list[dict]:
    conn = get_db_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT role, content
        FROM messages
        WHERE conversation_id = (
            SELECT id
            FROM conversations
            WHERE owner_id = (
                SELECT id FROM users WHERE session_id = %s
            )
        )
        ORDER BY created_at ASC
        """,
        (session_id,),
    )

    rows = cur.fetchall()
    conn.close()

    return [{"role": r[0], "content": r[1]} for r in rows if r[1]]
