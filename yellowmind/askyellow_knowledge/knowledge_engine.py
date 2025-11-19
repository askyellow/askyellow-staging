import os
import json
import unicodedata

# Map waar alle AskYellow kennisbestanden staan
# (Dennis kan dit aanpassen aan jullie structuur)
KNOWLEDGE_PATH = "yellowmind/askyellow_knowledge/"


# -----------------------------
# 1. CLEAN & NORMALISE TEXT
# -----------------------------
def normalize(text: str) -> str:
    """
    Maakt tekst geschikt voor eenvoudige matching:
    - lowercasing
    - accenten verwijderen (é -> e)
    - basisleestekens eruit
    - dubbele spaties weg
    """
    if not isinstance(text, str):
        text = str(text or "")

    text = text.lower().strip()

    # Remove accents (é → e)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()

    # Remove punctuation
    chars_to_remove = ".,!?;:()[]{}\"'"
    for c in chars_to_remove:
        text = text.replace(c, " ")

    # Remove double spaces
    while "  " in text:
        text = text.replace("  ", " ")

    return text.strip()


# -----------------------------
# 2. LOAD ALL KNOWLEDGE FILES
# -----------------------------
def load_knowledge():
    """
    Laadt alle JSON-bestanden in KNOWLEDGE_PATH en verzamelt hun 'entries'.

    Verwacht JSON-structuur:
    {
      "entries": [
        {
          "patterns": ["vraagvorm 1", "vraagvorm 2", ...],
          "answer": "Het antwoord in gewone tekst"
          // optioneel extra velden zoals 'category', 'tags' etc.
        },
        ...
      ]
    }
    """
    entries = []

    if not os.path.isdir(KNOWLEDGE_PATH):
        print(f"[knowledge_engine] WARNING: KNOWLEDGE_PATH bestaat niet: {KNOWLEDGE_PATH}")
        return entries

    for file in os.listdir(KNOWLEDGE_PATH):
        if not file.endswith(".json"):
            continue

        full_path = os.path.join(KNOWLEDGE_PATH, file)
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            file_entries = data.get("entries", [])
            if not isinstance(file_entries, list):
                print(f"[knowledge_engine] WARNING: 'entries' is geen lijst in {file}")
                continue

            # Eventueel: categorie op basis van bestandsnaam bijvoegen
            category = os.path.splitext(file)[0]  # bv. 'knowledge_shop'
            for e in file_entries:
                # Zorg dat basisvelden bestaan
                if "patterns" not in e or "answer" not in e:
                    print(f"[knowledge_engine] WARNING: entry zonder 'patterns' of 'answer' in {file}")
                    continue

                # Optioneel: interne categorie-tag
                if "category" not in e:
                    e["category"] = category

                entries.append(e)

        except Exception as e:
            print(f"[knowledge_engine] Error loading {file}: {e}")

    print(f"[knowledge_engine] Loaded {len(entries)} knowledge entries from {KNOWLEDGE_PATH}")
    return entries


# -----------------------------
# 3. MATCHING ENGINE (fuzzy)
# -----------------------------
def match_question(user_question: str, entries):
    """
    Zoekt naar een passend kennisantwoord op basis van:
    1) Exacte match: normalized(pattern) == normalized(vraag)
    2) Deels: normalized(pattern) is substring van normalized(vraag)
    3) Keyword overlap: minstens 2 gedeelde woorden

    Retourneert:
    - de 'answer'-string van de eerste goede match
    - of None als er niets passends is
    """
    if not user_question:
        return None

    nq = normalize(user_question)

    # 1. Exact keyword match
    for entry in entries:
        patterns = entry.get("patterns", [])
        answer = entry.get("answer")
        if not answer or not patterns:
            continue

        for p in patterns:
            if normalize(p) == nq:
                return answer

    # 2. Partial match (pattern contained in question)
    for entry in entries:
        patterns = entry.get("patterns", [])
        answer = entry.get("answer")
        if not answer or not patterns:
            continue

        for p in patterns:
            np = normalize(p)
            if len(np) > 3 and np in nq:
                return answer

    # 3. Keyword overlap (shared words)
    q_words = set(nq.split())

    for entry in entries:
        patterns = entry.get("patterns", [])
        answer = entry.get("answer")
        if not answer or not patterns:
            continue

        for p in patterns:
            p_words = set(normalize(p).split())
            overlap = q_words.intersection(p_words)

            # vereis minstens 2 overlappende woorden
            if len(overlap) >= 2:
                return answer

    # Geen match → laat het LLM het oppakken
    return None
