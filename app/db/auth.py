from app.db.models import get_db_conn

def get_auth_user_from_session(conn, session_id: str) -> int | None:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT user_id
        FROM auth_sessions
        WHERE session_id = %s
        """,
        (session_id,)
    )
    row = cur.fetchone()
    if not row:
        return None

    # 🔒 KEIHARD: ALTIJD INT
    return int(row[0])

