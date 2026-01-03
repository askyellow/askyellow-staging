from fastapi import APIRouter, Request, HTTPException
from app.db.models import get_db_conn
from app.db.auth import get_auth_user_from_session  # of waar hij staat

router = APIRouter()

# ---- Image Generation Tool ----

# ===== IMAGE GENERATION AUTH CHECK =====

def require_auth_session(request: Request):
    # 👇 PRE-FLIGHT ALTIJD TOESTAAN
    if request.method == "OPTIONS":
        return

    session_id = request.headers.get("X-Session-Id") or ""
    if not session_id:
        raise HTTPException(
            status_code=403,
            detail="Login vereist voor image generation"
        )

    conn = get_db_conn()
    user = get_auth_user_from_session(conn, session_id)
    conn.close()

    if not user:
        raise HTTPException(
            status_code=403,
            detail="Ongeldige of verlopen sessie"
        )


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