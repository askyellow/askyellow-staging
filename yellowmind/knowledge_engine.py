import os
import json
import unicodedata

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

KNOWLEDGE_PATH = os.path.join(BASE_DIR, "askyellow_knowledge")



# -----------------------------
# 1. CLEAN & NORMALISE TEXT
# -----------------------------
def normalize(text):
    text = text.lower().strip()

    # Remove accents (é → e)
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()

    # Remove punctuation
    chars_to_remove = ".,!?;:()[]{}\"'"
    for c in chars_to_remove:
        text = text.replace(c, " ")

    # Remove double spaces
    while "  " in text:
        text = text.replace("  ", " ")

    return text


# -----------------------------
# 2. LOAD ALL KNOWLEDGE FILES
# -----------------------------
def load_knowledge():
    entries = []

    # Loop through all .json files
    for file in os.listdir(KNOWLEDGE_PATH):
        if file.endswith(".json"):
            full_path = os.path.join(KNOWLEDGE_PATH, file)
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "entries" in data:
                        entries.extend(data["entries"])
            except Exception as e:
                print(f"Error loading {file}: {e}")

    return entries


# -----------------------------
# 3. MATCHING ENGINE (fuzzy)
# -----------------------------
def match_question(user_question, entries):
    nq = normalize(user_question)

    # 1. Exact keyword match
    for entry in entries:
        for p in entry["patterns"]:
            if normalize(p) == nq:
                return entry["answer"]

    # 2. Partial match (pattern contained in question)
    for entry in entries:
        for p in entry["patterns"]:
            if normalize(p) in nq and len(normalize(p)) > 3:
                return entry["answer"]

    # 3. Keyword overlap (shared words)
    q_words = set(nq.split())

    for entry in entries:
        for p in entry["patterns"]:
            p_words = set(normalize(p).split())
            overlap = q_words.intersection(p_words)

            # we require at least 2 overlapping words
            if len(overlap) >= 2:
                return entry["answer"]

    return None  # fallback to AI
