# constraint_extractor.py

from openai import OpenAI
import json

client = OpenAI()


def build_constraint_prompt(conversation_text: str) -> list:
    system_prompt = """
Je taak is om uit onderstaande conversatie producteisen te extraheren.

Geef uitsluitend geldige JSON in dit exacte formaat:

{
  "category": string | null,
  "budget_min": number | null,
  "budget_max": number | null,
  "requirements": {},
  "preferences": {}
}

Regels:
- Interpreteer budget-taal:
  - "onder de X" → budget_max = X
  - "boven de X" → budget_min = X
  - "tussen X en Y" → budget_min = X, budget_max = Y
  - "ongeveer X" → budget_max = X
- Gebruik alleen numerieke waarden voor budget.
- Geen tekst buiten JSON.
- Geen productnamen.
- Geen uitleg.
- Als iets niet bekend is → null.
"""

    user_prompt = f"""
Conversatie:
{conversation_text}

Extraheer de producteisen.
"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

def extract_constraints(conversation_text: str) -> dict:
    messages = build_constraint_prompt(conversation_text)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.2  # laag voor stabiliteit
    )

    content = response.choices[0].message.content.strip()

    try:
        return json.loads(content)
    except Exception:
        return {
            "category": None,
            "budget_min": None,
            "budget_max": None,
            "requirements": {},
            "preferences": {}
        }

def normalize_constraints(raw: dict) -> dict:
    constraints = {
        "category": raw.get("category"),
        "budget_min": raw.get("budget_min"),
        "budget_max": raw.get("budget_max"),
        "requirements": raw.get("requirements") or {},
        "preferences": raw.get("preferences") or {}
    }

    # Budget sanity checks
    if constraints["budget_min"] is not None:
        try:
            constraints["budget_min"] = float(constraints["budget_min"])
        except:
            constraints["budget_min"] = None

    if constraints["budget_max"] is not None:
        try:
            constraints["budget_max"] = float(constraints["budget_max"])
        except:
            constraints["budget_max"] = None

    # Negatieve bedragen blokkeren
    if constraints["budget_min"] is not None and constraints["budget_min"] < 0:
        constraints["budget_min"] = None

    if constraints["budget_max"] is not None and constraints["budget_max"] < 0:
        constraints["budget_max"] = None

    return constraints

def extract_and_normalize(conversation_text: str) -> dict:
    raw = extract_constraints(conversation_text)
    return normalize_constraints(raw)
