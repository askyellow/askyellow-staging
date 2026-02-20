from fastapi import APIRouter
from .analyzer import ai_analyze_input
from .analyzer import ai_generate_refinement_question
from .analyzer import ai_generate_targeted_question
from search_v2.query_builder import ai_build_search_decision
from search_v2.state import get_conversation, add_message


router = APIRouter(prefix="/search_v2", tags=["search_v2"])

from search_v2.state import get_or_create_state, merge_analysis_into_state

from search_v2.query_builder import ai_build_search_decision
from search_v2.state import get_conversation, add_message

@router.post("/analyze")
async def analyze_v2(data: dict):
    session_id = data.get("session_id", "demo")
    query = (data.get("query") or "").strip()

    # 1️⃣ User message opslaan
    add_message(session_id, "user", query)

    # 2️⃣ Volledige conversatie ophalen
    conversation = get_conversation(session_id)

    # 3️⃣ AI laten beslissen
    decision = ai_build_search_decision(conversation)

    if not decision["is_ready_to_search"]:
        # 4️⃣ Assistant vraag opslaan
        add_message(session_id, "assistant", decision["clarification_question"])

        return {
            "action": "ask",
            "question": decision["clarification_question"],
            "confidence": decision["confidence"]
        }

    # 5️⃣ Assistant search-zin opslaan
    add_message(session_id, "assistant", decision["proposed_query"])

    return {
        "action": "search",
        "query": decision["proposed_query"],
        "confidence": decision["confidence"]
    }
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
