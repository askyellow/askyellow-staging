# search_v2/query_builder.py

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

client = OpenAI()

SYSTEM_PROMPT = """
Je bent een ervaren verkoopmedewerker in een webshop.

Je doel is niet alleen zoeken, maar de klant zo goed mogelijk helpen om het juiste product te vinden.

Je krijgt een volledige conversatie tussen jou en de klant.

Jouw taak:

1. Begrijp wat de klant werkelijk zoekt.
2. Integreer alle antwoorden die de klant heeft gegeven.
3. Bepaal of je voldoende informatie hebt om relevante producten te tonen.
4. Als belangrijke product-definiërende eigenschappen nog ontbreken, stel EXACT 1 gerichte en logische vervolgvraag.
5. Als je voldoende informatie hebt, genereer één optimale zoekzin voor een webshop of zoekmachine.

Belangrijk:

- Herhaal nooit iets wat de klant al expliciet heeft gezegd.
- Stel geen overbodige of algemene vragen.
- Vraag alleen door als het ontbreken van informatie waarschijnlijk tot verkeerde of irrelevante producten leidt.
- Denk als een verkoper: toon pas producten als je er redelijk zeker van bent dat ze passend zijn.
- Wees natuurlijk en kort in je vraagstelling.

Definieer "voldoende informatie" als:
De zoekzin is specifiek genoeg dat de kans klein is dat de verkeerde productcategorie of een verkeerd producttype wordt getoond.

Antwoord uitsluitend in geldig JSON met dit formaat:

{
  "proposed_query": "string or null",
  "is_ready_to_search": true or false,
  "confidence": 0.0-1.0,
  "clarification_question": "string or null"
}

Regels:
- Als is_ready_to_search = true → proposed_query moet gevuld zijn en clarification_question moet null zijn.
- Als is_ready_to_search = false → clarification_question moet gevuld zijn en proposed_query moet null zijn.
- confidence geeft aan hoe zeker je bent dat de informatie voldoende is om goede producten te tonen.
- Geen uitleg buiten JSON.

Beoordeel streng.

Als er meerdere productvarianten bestaan die sterk verschillen op basis van gebruikssituatie
(bijvoorbeeld muur vs plafond, binnen vs buiten, vochtbelasting, ondergrondtype),
dan is de informatie NIET voldoende.

Wees conservatief:
Stel liever één gerichte vervolgvraag dan te vroeg producten tonen.

Zet is_ready_to_search alleen op true als een ervaren verkoopmedewerker
met vertrouwen direct producten zou laten zien.
""".strip()


# ----------------------------
# Helpers
# ----------------------------

_CODE_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE | re.MULTILINE)


def _strip_code_fences(text: str) -> str:
    return _CODE_FENCE_RE.sub("", text).strip()


def _safe_json_loads(text: str) -> Dict[str, Any]:
    """
    Try to parse JSON even if model adds extra text (we disallow it, but be resilient).
    """
    text = _strip_code_fences(text)

    # If the model accidentally adds leading/trailing junk, try to extract the first JSON object.
    if not text.startswith("{"):
        start = text.find("{")
        if start != -1:
            text = text[start:]
    if not text.endswith("}"):
        end = text.rfind("}")
        if end != -1:
            text = text[: end + 1]

    return json.loads(text)


def _normalize_decision(d: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate required keys, types, and contract invariants.
    Raises ValueError if not valid.
    """
    required = {"proposed_query", "is_ready_to_search", "confidence", "clarification_question"}
    missing = required - set(d.keys())
    if missing:
        raise ValueError(f"Missing keys: {sorted(missing)}")

    is_ready = d["is_ready_to_search"]
    if not isinstance(is_ready, bool):
        raise ValueError("is_ready_to_search must be boolean")

    conf = d["confidence"]
    if not isinstance(conf, (int, float)):
        raise ValueError("confidence must be a number")
    conf = float(conf)
    if conf < 0.0:
        conf = 0.0
    if conf > 1.0:
        conf = 1.0

    pq = d["proposed_query"]
    cq = d["clarification_question"]

    if pq is not None and not isinstance(pq, str):
        raise ValueError("proposed_query must be string or null")
    if cq is not None and not isinstance(cq, str):
        raise ValueError("clarification_question must be string or null")

    # Contract: if ready => pq filled, cq null
    if is_ready:
        if not pq or not pq.strip():
            raise ValueError("is_ready_to_search=true but proposed_query is empty")
        if cq is not None and cq.strip():
            raise ValueError("is_ready_to_search=true but clarification_question is not null/empty")
        pq = pq.strip()
        cq = None
    else:
        if not cq or not cq.strip():
            raise ValueError("is_ready_to_search=false but clarification_question is empty")
        if pq is not None and pq.strip():
            raise ValueError("is_ready_to_search=false but proposed_query is not null/empty")
        cq = cq.strip()
        pq = None

    return {
        "proposed_query": pq,
        "is_ready_to_search": is_ready,
        "confidence": conf,
        "clarification_question": cq,
    }


def _conversation_to_text(conversation_history):
    lines = []
    for msg in conversation_history[-12:]:
        role = msg["role"]
        content = msg["content"]
        lines.append(f"{role.upper()}: {content}")
    return "\n".join(lines)

# ----------------------------
# Main function
# ----------------------------

def ai_build_search_decision(
    conversation_history: List[str],
    model: str = "gpt-4.1-mini",
    temperature: float = 0.0,
    max_retries: int = 2,
) -> Dict[str, Any]:
    """
    Returns dict:
      - proposed_query (str|None)
      - is_ready_to_search (bool)
      - confidence (float 0..1)
      - clarification_question (str|None)

    Robust to minor formatting errors; retries with stricter instruction.
    """
    transcript = _conversation_to_text(conversation_history)

    user_prompt = f"""
Conversatie:
{transcript}
""".strip()

    last_err: Optional[str] = None

    for attempt in range(max_retries + 1):
        extra = ""
        if attempt > 0:
            extra = f"""
Let op: Je vorige antwoord was ongeldig ({last_err}).
Geef nu ALLEEN geldig JSON dat exact voldoet aan het schema en de regels. Geen extra tekst.
""".strip()

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt + ("\n\n" + extra if extra else "")},
        ]

        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
        )

        raw = (resp.choices[0].message.content or "").strip()

        try:
            parsed = _safe_json_loads(raw)
            normalized = _normalize_decision(parsed)
            return normalized
        except Exception as e:
            last_err = str(e)
            continue

    # Hard fallback: ask a generic but non-dumb clarify question (still not hardcoded per category)
    return {
        "proposed_query": None,
        "is_ready_to_search": False,
        "confidence": 0.0,
        "clarification_question": "Kun je één detail toevoegen zodat ik zeker weet welk type je bedoelt?",
    }