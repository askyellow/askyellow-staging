import re
import time

# =============================================================
# 🔍 SEARCH INTENT DETECTION
# =============================================================

SEARCH_TRIGGERS = [
    "opzoeken",
    "op zoek",
    "meest verkocht",
    "dit jaar",
    "dit moment",
    "actueel",
    "nu populair",
    "trending",
    "beste",
    "vergelijk",
    "waar koop",
    "waar kan ik",
]

def detect_search_intent(question: str) -> bool:
    q = question.lower()
    return any(trigger in q for trigger in SEARCH_TRIGGERS)


# =============================================================
# IMAGE INTENT DETECTION
# =============================================================

def detect_image_intent(question: str) -> bool:
    triggers = [
        "genereer",
        "afbeelding",
        "plaatje",
        "beeld",
        "image",
        "illustratie",
    ]
    return any(t in question.lower() for t in triggers)


# =============================================================
# 🧠 CONTEXT / MODE HINTS
# =============================================================

def detect_hints(question: str) -> dict:
    q = question.lower()

    mode = "auto"
    context = "general"
    user = None

    if any(x in q for x in ["api", "bug", "foutmelding", "script", "dns"]):
        mode = "tech"

    if any(x in q for x in ["askyellow", "yellowmind", "logo", "branding"]):
        mode = "branding"
        context = "askyellow"

    if any(x in q for x in ["ik voel me", "overprikkeld", "huil"]):
        mode = "empathy"
        user = "emotioneel"

    return {
        "mode_hint": mode,
        "context_type": context,
        "user_type_hint": user,
    }


# =============================================================
# ⚙️ PERFORMANCE STATUS CHECK
# =============================================================

def detect_cold_start(sql_ms: int, kb_ms: int, ai_ms: int, total_ms: int) -> str:
    if ai_ms > 6000:
        return "🔥 COLD START — model wakker gemaakt"
    if sql_ms > 800:
        return "❄️ SLOW SQL"
    if kb_ms > 200:
        return "⚠️ KB slow"
    if total_ms > 5000:
        return "⏱️ Slow total"
    return "✓ warm"


def log_ai_status(ai_ms: int):
    status = detect_cold_start(0, 0, ai_ms, ai_ms)
    print(f"[STATUS] {status} | AI {ai_ms} ms")
