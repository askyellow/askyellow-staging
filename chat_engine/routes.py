
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from chat_engine.db import get_conn
from chat_engine.utils import get_logical_date

router = APIRouter()

class ChatSendPayload(BaseModel):
    session_id: str
    message: str

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
        row = cur.fetchone()
        if row:
            session_id = row["id"]
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
        return {
            "session_id": session_id,
            "messages": messages,
            "session_date": str(logical_date)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/send")
def send_chat(payload: ChatSendPayload):
    try:
        conn = get_conn()
        cur = conn.cursor()
        # sla userbericht op
        cur.execute(
            "INSERT INTO chat_messages (session_id, role, content) VALUES (%s, %s, %s);",
            (payload.session_id, "user", payload.message)
        )
        conn.commit()
        # TODO: hier straks AI-logica koppelen (OpenAI / ask-endpoint)
        dummy_answer = "Chat-engine is gekoppeld, maar de AI-logica moet hier nog worden aangesloten. 🙂"
        cur.execute(
            "INSERT INTO chat_messages (session_id, role, content) VALUES (%s, %s, %s);",
            (payload.session_id, "assistant", dummy_answer)
        )
        conn.commit()
        return {"answer": dummy_answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
