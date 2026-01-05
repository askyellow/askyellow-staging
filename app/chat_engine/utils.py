import time
import re
import unicodedata
import requests
import os
from datetime import datetime, timedelta
import pytz

SQL_SEARCH_URL = os.getenv("SQL_SEARCH_URL")

def get_logical_date():
    tz = pytz.timezone("Europe/Amsterdam")
    now = datetime.now(tz)
    if now.hour < 3:
        return (now - timedelta(days=1)).date()
    return now.date()

_APP_STARTED_AT = time.time()
_COLD_START_WINDOW = 15  # seconden

def detect_cold_start() -> bool:
    """
    Returns True if we're likely in a cold start window.
    """
    return (time.time() - _APP_STARTED_AT) < _COLD_START_WINDOW


# =============================================================
# 4. SQL KNOWLEDGE LAYER
# =============================================================

def normalize(text: str) -> str:
    text = text.lower().strip()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text

def jaccard_score(a: str, b: str) -> float:
    wa = set(normalize(a).split())
    wb = set(normalize(b).split())
    if not wa or not wb:
        return 0.0
    inter = wa.intersection(wb)
    union = wa.union(wb)
    return len(inter) / len(union)

def compute_match_score(user_q: str, cand_q: str) -> int:
    j = jaccard_score(user_q, cand_q)
    contains = 1.0 if normalize(cand_q) in normalize(user_q) else 0.0
    score = int((0.7 * j + 0.3 * contains) * 100)
    return max(0, min(score, 100))

def search_sql_knowledge(question: str):
    try:
        resp = requests.post(SQL_SEARCH_URL, data={"q": question}, timeout=3)
        if resp.status_code != 200:
            print("⚠ SQL STATUS:", resp.status_code)
            return None
        data = resp.json()
    except Exception as e:
        print("⚠ SQL ERROR:", e)
        return None

    best = None
    best_score = 0

    for row in data:
        # 🔒 robuust: werkt voor dict én string
        row_question = (
            row.get("question") if isinstance(row, dict)
            else row
        )

        score = compute_match_score(question, row_question or "")

        if score > best_score:
            best_score = score
            best = {
                "id": row.get("id") if isinstance(row, dict) else None,
                "question": row_question or "",
                "answer": row.get("answer") if isinstance(row, dict) else "",
                "score": score
            }

    # ⬅️ DIT hoort nog binnen de functie
    if best:
        print(f"🤖 SQL BEST MATCH SCORE={best_score}")
        return best

    return None


def wants_image(text: str) -> bool:
    if not text:
        return False

    t = text.lower()

    triggers = [
        "maak een afbeelding",
        "genereer een afbeelding",
        "genereer image",
        "generate image",
        "image of",
        "picture of",
        "teken",
        "plaatje",
        "afbeelding",
    ]

    return any(trigger in t for trigger in triggers)
