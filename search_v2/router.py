from fastapi import APIRouter
from .analyzer import ai_analyze_input
from .analyzer import ai_generate_refinement_question

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

    # ===============================
    # MODE 1 – ASSISTED SEARCH
    # ===============================

    if state.get("intent") == "assisted_search":

        # als nog geen refinement gedaan → inhoudelijke vraag
        if not state.get("refinement_done"):
            question = ai_generate_refinement_question(state)
            state["refinement_done"] = True
            return {
                "action": "ask",
                "question": question,
                "state": state
            }

        # na refinement → wacht op verdere specificatie
        # GEEN automatische budget push
        return {
            "action": "ask",
            "question": ai_generate_refinement_question(state),
            "state": state
        }


    # ===============================
    # MODE 2 – DIRECT PRODUCT SEARCH
    # ===============================

    if state.get("intent") == "product_search":

        # refinement vóór search indien nuttig
        if should_refine(state):
            question = ai_generate_refinement_question(state)
            state["refinement_done"] = True
            return {
                "action": "ask",
                "question": question,
                "state": state
            }

        # als category + budget bekend → search
        if (
            state.get("category")
            and state["constraints"].get("price_max") is not None
        ):
            return {
                "action": "search",
                "state": state
            }

        # category ontbreekt
        if not state.get("category"):
            return {
                "action": "ask",
                "question": "Waar ben je naar op zoek?",
                "state": state
            }

        # budget ontbreekt (alleen bij product_search)
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
