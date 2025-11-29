
from fastapi import APIRouter, HTTPException
from chat_engine.db import get_conn
from chat_engine.utils import get_logical_date

router = APIRouter()

@router.post("/start")
def start_chat(user_id: str):
    logical_date = get_logical_date()
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM chat_sessions WHERE user_id=%s AND session_date=%s AND is_active=TRUE LIMIT 1;",
            (user_id, logical_date)
        )
        result = cur.fetchone()
        if result:
            session_id = result["id"]
        else:
            cur.execute(
                "INSERT INTO chat_sessions (user_id, session_date) VALUES (%s, %s) RETURNING id;",
                (user_id, logical_date)
            )
            session_id = cur.fetchone()["id"]
            conn.commit()
        cur.execute(
            "SELECT role, content, created_at FROM chat_messages WHERE session_id=%s ORDER BY created_at ASC LIMIT 20;",
            (session_id,)
        )
        messages = cur.fetchall()
        return {"session_id": session_id, "messages": messages, "session_date": str(logical_date)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
