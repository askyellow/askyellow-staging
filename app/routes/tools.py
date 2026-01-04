from fastapi import APIRouter, Request, HTTPException
from app.services.auth import require_auth_session
from app.services.image import generate_image

router = APIRouter()

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
