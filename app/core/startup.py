# app/core/startup.py

from app.db.models import init_db
from app.yellowmind.knowledge_engine import load_knowledge

KNOWLEDGE_ENTRIES = None


def on_startup():
    global KNOWLEDGE_ENTRIES

    # 1️⃣ Database init
    init_db()

    # 2️⃣ Knowledge laden
    KNOWLEDGE_ENTRIES = load_knowledge()

def get_knowledge_entries():
    global KNOWLEDGE_ENTRIES

    if KNOWLEDGE_ENTRIES is None:
        print("⚠️ Knowledge not loaded yet — loading lazily")
        KNOWLEDGE_ENTRIES = load_knowledge()

    return KNOWLEDGE_ENTRIES
