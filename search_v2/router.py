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

    return {
        "analysis": analysis,
        "state": state
    }
