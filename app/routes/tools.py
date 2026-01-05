from fastapi import APIRouter, Request, HTTPException
from app.services.auth import require_auth_session
from app.services.image import generate_image
from pydantic import BaseModel
from app.services.utils import search_sql_knowledge

router = APIRouter()

print("🔥 TOOLS ROUTER LOADED 🔥")

@router.post("/image_generate")
async def tool_image_generate(request: Request, payload: dict):
    require_auth_session(request)

    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Missing prompt")

    url = generate_image(prompt)

    return {
        "tool": "image_generate",
        "prompt": prompt,
        "url": url,
    }

class ToolPayload(BaseModel):
    query: str

@router.post("/knowledge_search")
def tool_knowledge_search(payload: ToolPayload):
    result = search_sql_knowledge(payload.query)
    return {
        "tool": "knowledge_search",
        "result": result
    }


@router.post("/websearch")
def tool_websearch(payload: ToolPayload):
    # later echte websearch
    return {
        "tool": "websearch",
        "result": None
    }


@router.post("/shopify_search")
def tool_shopify_search(payload: ToolPayload):
    # later echte shopify logica
    return {
        "tool": "shopify_search",
        "result": None
    }
