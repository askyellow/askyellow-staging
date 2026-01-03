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

def on_startup():
    global KNOWLEDGE_ENTRIES

    print("🚀 Startup: init_db()")
    init_db()

    print("📚 Startup: load_knowledge()")
    KNOWLEDGE_ENTRIES = load_knowledge()

    print(
        "✅ Startup complete | "
        f"Knowledge loaded: {KNOWLEDGE_ENTRIES is not None}"
    )
