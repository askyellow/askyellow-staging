from app.identity_origin import try_identity_origin_answer
from app.chat_engine.utils import search_sql_knowledge
from app.knowledge.engine import match_question, KNOWLEDGE_ENTRIES

def build_context(question: str, language: str) -> dict:
    identity_answer = try_identity_origin_answer(question, language)

    sql_match = search_sql_knowledge(question)

    try:
        kb_answer = match_question(question, KNOWLEDGE_ENTRIES)
    except Exception:
        kb_answer = None

    return {
        "identity_answer": identity_answer,
        "sql_match": sql_match,
        "kb_answer": kb_answer,
        "hints": {},
    }
