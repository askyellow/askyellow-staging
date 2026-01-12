from app.db.models import get_db_conn

def get_auth_user_from_session(conn, session_id):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id
        FROM users
        WHERE session_id = %s
        """,
        (session_id,)
    )
    row = cur.fetchone()
    if not row:
        return None

    # 👇 DIT IS CRUCIAAL
    if isinstance(row, dict):
        return {"id": int(row["id"])}
    else:
        return {"id": int(row[0])}
