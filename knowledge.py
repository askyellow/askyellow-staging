# knowledge.py
from knowledge_engine import load_knowledge, match_question

KNOWLEDGE_ENTRIES = load_knowledge()

def search_knowledge(query: str):
    return match_question(query, KNOWLEDGE_ENTRIES)
