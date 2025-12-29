from app.db.models import get_db_conn

def get_auth_user_from_session(conn, session_id: str):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT u.*
        FROM auth_sessions s
        JOIN auth_users u ON u.id = s.user_id
        WHERE s.session_id = %s
          AND s.expires_at > NOW()
        """,
        (session_id,)
    )
    return cur.fetchone()
