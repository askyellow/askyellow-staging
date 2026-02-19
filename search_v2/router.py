from fastapi import APIRouter
from .analyzer import ai_analyze_input

router = APIRouter(prefix="/search_v2", tags=["search_v2"])

from search_v2.state import get_or_create_state, merge_analysis_into_state

@router.post("/analyze")
async def analyze_v2(data: dict):
    session_id = data.get("session_id", "demo")
    query = data.get("query", "")

    analysis = ai_analyze_input(query)

    state = get_or_create_state(session_id)
    state = merge_analysis_into_state(state, analysis)

    print("ANALYSIS:", analysis)
    print("STATE:", state)

    # 🔥 REFINEMENT CHECK
    if should_refine(state):
        question = ai_generate_refinement_question(state)
        state["refinement_done"] = True
        return {
            "action": "ask",
            "question": question,
            "state": state
        }

    # 🔥 SEARCH CHECK
    if (
        state.get("intent") in ["search", "search_product"]
        and state.get("category")
        and state["constraints"].get("price_max") is not None
    ):
        return {
            "action": "search",
            "state": state
        }

    # 🔥 FALLBACKS
    if not state.get("category"):
        return {
            "action": "ask",
            "question": "Waar ben je naar op zoek?",
            "state": state
        }

    return {
        "action": "ask",
        "question": "Wat is je maximale budget?",
        "state": state
    }

def should_refine(state):
    if state.get("refinement_done"):
        return False

    if state.get("intent") not in ["search", "search_product"]:
        return False

    if not state.get("category"):
        return False

    if state["constraints"].get("price_max") is None:
        return False

    return True
