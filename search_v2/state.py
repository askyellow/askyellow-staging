from typing import Dict, Any

# Simpele in-memory store (later vervangen door Redis of DB)
SEARCH_STATES: Dict[str, Dict[str, Any]] = {}


def get_or_create_state(session_id: str) -> Dict[str, Any]:
    if session_id not in SEARCH_STATES:
        SEARCH_STATES[session_id] = {
            "intent": None,
            "category": None,
            "constraints": {
                "price_max": None,
                "keywords": []
            },
            "refinement_done": False
            }
    return SEARCH_STATES[session_id]


def merge_analysis_into_state(state: Dict[str, Any], analysis: Dict[str, Any]):
    # Intent
    if analysis.get("intent"):
        state["intent"] = analysis["intent"]

    # Category
    if analysis.get("category"):
        state["category"] = analysis["category"]

    new_constraints = analysis.get("new_constraints", {})

    # price_max overschrijven indien aanwezig
    if "price_max" in new_constraints:
        state["constraints"]["price_max"] = new_constraints["price_max"]

    # keywords uitbreiden (unique)
    if "keywords" in new_constraints:
        existing = set(state["constraints"]["keywords"])
        for kw in new_constraints["keywords"]:
            existing.add(kw)
        state["constraints"]["keywords"] = list(existing)

    return state
