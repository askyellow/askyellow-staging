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


    def should_refine(state, analysis):
        # refinement alleen vóór eerste search
        if state.get("refinement_done"):
            return False

        # alleen als we al basis hebben
        if state.get("intent") != "search":
            return False
        if not state.get("category"):
            return False
        if state["constraints"].get("price_max") is None:
            return False

        # geen refinement op negatieve antwoorden
        if analysis.get("is_negative"):
            return False

        return bool(analysis.get("should_refine")) and bool(analysis.get("refine_question"))


    def should_search(state):
        return (
            state["intent"] == "search"
            and state["category"] is not None
            and state["constraints"]["price_max"] is not None
        )

    if should_search(state):
        return {
            "action": "search",
            "state": state
        }
    else:
        return {
            "action": "ask",
            "question": "Wat is je maximale budget?",
            "state": state
        }

