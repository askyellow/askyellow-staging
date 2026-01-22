from fastapi import APIRouter, Request, HTTPException
from image_shared import (
    wants_image,
    generate_image,
    detect_intent,
    require_auth_session,
    handle_image_intent,
    )
router = APIRouter()


@router.post("/tool/image_generate")
async def tool_image_generate(request: Request, payload: dict):
    require_auth_session(request)

    """Genereert een afbeelding via OpenAI gpt-image-1 model."""
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Missing prompt")

    try:
        result = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size="1024x1024",
        )
        url = result.data[0].url
    except Exception as e:
        print("🔥 IMAGE GENERATION ERROR 🔥")
        print(traceback.format_exc())
        raise HTTPException(
        status_code=500,
        detail=str(e)
    )

    return {
        "tool": "image_generate",
        "prompt": prompt,
        "url": url,
    }
