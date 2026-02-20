from fastapi import APIRouter
from .analyzer import ai_analyze_input
from .analyzer import ai_generate_refinement_question
from .analyzer import ai_generate_targeted_question
from search_v2.query_builder import ai_build_search_decision
from search_v2.state import get_conversation, add_to_conversation


router = APIRouter(prefix="/search_v2", tags=["search_v2"])

from search_v2.state import get_or_create_state, merge_analysis_into_state

@router.post("/analyze")
async def analyze_v2(data: dict):
    session_id = data.get("session_id", "demo")
    query = data.get("query", "")

    state = get_or_create_state(session_id)
    analysis = ai_analyze_input(query, state)
    state = merge_analysis_into_state(state, analysis)


    print("ANALYSIS:", analysis)
    print("STATE:", state)

    conversation = get_conversation(session_id)
    conversation.append(query)

    decision = ai_build_search_decision(conversation)

    if decision["action"] == "clarify":
        return {"action": "ask", "question": decision["clarification_question"]}

    if decision["action"] == "search":
        return {"action": "search", "query": decision["search_query"]}


    # ===============================
    # ASSISTED MODE
    # ===============================
    

    # if state.get("intent") == "assisted_search":

    #     # Category moet bestaan
    #     if not state.get("category"):
    #         return {
    #             "action": "error",
    #             "message": "Category detection failed",
    #             "state": state
    #         }

    #     # Als er nog informatie ontbreekt → gerichte vraag
    #     if analysis.get("missing_info"):
    #         question = ai_generate_targeted_question(
    #             state,
    #             analysis["missing_info"],
    #             query
    #         )
    #         return {
    #             "action": "ask",
    #             "question": question,
    #             "state": state
    #         }

    #     # GEEN automatische search in assisted mode
    #     # Blijf inhoudelijk doorvragen
    #     question = ai_generate_targeted_question(
    #         state,
    #         ["specifieke toepassing of eigenschappen"],
    #         query
    #     )

    #     return {
    #         "action": "ask",
    #         "question": question,
    #         "state": state
    #     }


    # if state.get("intent") == "product_search":

    #     if analysis.get("missing_info"):
    #         question = ai_generate_targeted_question(
    #             state,
    #             analysis["missing_info"],
    #             query
    #         )
    #         return {
    #             "action": "ask",
    #             "question": question,
    #             "state": state
    #         }

    #     if (
    #         state.get("category")
    #         and state["constraints"].get("price_max") is not None
    #     ):
    #         return {
    #             "action": "search",
    #             "state": state
    #         }

    #     if not state.get("category"):
    #         return {
    #             "action": "ask",
    #             "question": "Waar ben je naar op zoek?",
    #             "state": state
    #         }

    #     return {
    #         "action": "ask",
    #         "question": "Wat is je maximale budget?",
    #         "state": state
    #     }


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
