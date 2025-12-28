import os
import json
import unicodedata
from typing import List, Dict, Optional, Any

# Basisdirectory = map waar dit bestand zelf in staat
BASE_DIR = os.path.dirname(__file__)

# Map waar alle AskYellow kennisbestanden staan (naast knowledge_engine.py)
KNOWLEDGE_PATH = os.path.join(BASE_DIR, "askyellow_knowledge")


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
def load_knowledge() -> List[Dict[str, Any]]:
    """
    Laadt alle JSON-bestanden in KNOWLEDGE_PATH en verzamelt hun 'entries'.

    Verwacht JSON-structuur:
    {
      "entries": [
        {
          "patterns": ["vraagvorm 1", "vraagvorm 2", ...],
          "answer": "Het antwoord in gewone tekst",
          // optioneel extra velden zoals:
          // "category": "shop",
          // "lang": "nl",
          // "tags": ["..."],
          // etc.
        },
        ...
      ]
    }

    Aanvullingen door deze functie:
    - Als 'category' ontbreekt, wordt bestandsnaam (zonder .json) gebruikt.
    - Als 'lang' ontbreekt, wordt 'nl' als default gezet.
    - We voegen een intern veld '_source_file' toe met de bestandsnaam.
    """
    entries: List[Dict[str, Any]] = []

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

            # Categorie op basis van bestandsnaam, bv. 'knowledge_shop'
            base_category = os.path.splitext(file)[0]

            for e in file_entries:
                # Zorg dat basisvelden bestaan
                if "patterns" not in e or "answer" not in e:
                    print(f"[knowledge_engine] WARNING: entry zonder 'patterns' of 'answer' in {file}")
                    continue

                # Defaults & meta
                e.setdefault("category", base_category)
                e.setdefault("lang", "nl")  # veilig default; entries kunnen dit zelf overschrijven
                e["_source_file"] = file

                entries.append(e)

        except Exception as exc:
            print(f"[knowledge_engine] Error loading {file}: {exc}")

    print(f"[knowledge_engine] Loaded {len(entries)} knowledge entries from {KNOWLEDGE_PATH}")
    return entries


# -----------------------------
# 3. MATCHING ENGINE (fuzzy)
# -----------------------------
def _match_entry(user_question: str, entries: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Interne helper: zoekt de BESTE matchende entry voor een vraag.

    Matching-logica:
    1) Exacte match: normalized(pattern) == normalized(vraag)
    2) Deels: normalized(pattern) is substring van normalized(vraag)
    3) Keyword overlap: minstens 2 gedeelde woorden

    Retourneert:
    - de volledige entry-dict van de eerste goede match
    - of None als er niets passends is
    """
    if not user_question:
        return None

    nq = normalize(user_question)

    # 1. Exact keyword match
    for entry in entries:
        patterns = entry.get("patterns", [])
        if not patterns:
            continue

        for p in patterns:
            if normalize(p) == nq:
                return entry

    # 2. Partial match (pattern contained in question)
    for entry in entries:
        patterns = entry.get("patterns", [])
        if not patterns:
            continue

        for p in patterns:
            np = normalize(p)
            if len(np) > 3 and np in nq:
                return entry

    # 3. Keyword overlap (shared words)
    q_words = set(nq.split())

    for entry in entries:
        patterns = entry.get("patterns", [])
        if not patterns:
            continue

        for p in patterns:
            p_words = set(normalize(p).split())
            overlap = q_words.intersection(p_words)

            # vereis minstens 2 overlappende woorden
            if len(overlap) >= 2:
                return entry

    # Geen match → laat het LLM het oppakken
    return None


def match_question_entry(user_question: str, entries: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Publieke functie: geeft de volledige entry terug (answer + meta) bij een match.

    Gebruik dit als je in de backend:
    - niet alleen het antwoord,
    - maar ook category/lang/_source_file of andere velden wilt gebruiken.

    Retourneert:
    - dict met o.a. 'answer', 'patterns', 'category', 'lang', '_source_file'
    - of None als er geen match is.
    """
    return _match_entry(user_question, entries)


def match_question(user_question: str, entries: List[Dict[str, Any]]) -> Optional[str]:
    """
    Backwards-compatible helper:
    - Geeft alleen de 'answer'-string van de eerste goede match.
    - Of None als er niets passends is.

    Bestaande code die alleen een string verwacht, kan deze functie blijven gebruiken.
    Voor rijkere info kun je match_question_entry(...) aanroepen.
    """
    entry = _match_entry(user_question, entries)
    if entry is None:
        return None
    return entry.get("answer")
