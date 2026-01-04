from openai import OpenAI
from fastapi import HTTPException

_client = None

def get_client():
    global _client
    if _client is None:
        _client = OpenAI()
    return _client

def generate_image(prompt: str) -> dict:
    if not prompt.strip():
        raise HTTPException(status_code=400, detail="Empty image prompt")

    result = client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size="1024x1024",
    )

    if not result.data:
        raise HTTPException(status_code=502, detail=f"Image generation failed: {e}")

    return {
        "type": "image",
        "url": result.data[0].url,
    }
