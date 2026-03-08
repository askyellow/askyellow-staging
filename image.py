from fastapi import APIRouter, HTTPException, Request

from image_shared import generate_image, require_auth_session

router = APIRouter()


@router.post("/tool/image_generate")
async def tool_image_generate(request: Request, payload: dict):
    require_auth_session(request)

    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Missing prompt")

    url = generate_image(prompt)
    if not url:
        raise HTTPException(status_code=500, detail="Image generation failed")

    return {
        "tool": "image_generate",
        "prompt": prompt,
        "url": url,
    }