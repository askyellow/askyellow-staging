from app.db.connection import get_db_conn
from app.db.queries import (
    get_recent_messages,
    save_message,
)

def load_history_for_llm(session_id: str) -> list[dict]:
    """
    Geeft chatgeschiedenis terug in het formaat
    dat het LLM verwacht.
    """
    return get_recent_messages(session_id)

def persist_user_message(session_id: str, content: str):
    save_message(session_id, "user", content)

def persist_ai_message(session_id: str, content: str):
    save_message(session_id, "assistant", content)


