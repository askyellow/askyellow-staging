from fastapi import APIRouter
from .analyzer import ai_analyze_input

router = APIRouter(prefix="/search_v2", tags=["search_v2"])

@router.post("/analyze")
async def analyze_v2(data: dict):
    return ai_analyze_input(data.get("query", ""))
