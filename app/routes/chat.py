# app/routes/chat.py

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from app.chat_engine.engine import handle_chat_request  # bestaande logica
from app.core.sessions import get_or_create_session     # bestaande helper

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("")
async def chat(request: Request):
    data = await request.json()

    question = (data.get("question") or "").strip()
    session_id = (data.get("session_id") or "").strip()
    language = (data.get("language") or "nl").lower()

    if not question:
        raise HTTPException(status_code=400, detail="Geen vraag ontvangen")

    if not session_id:
        raise HTTPException(status_code=400, detail="Session ontbreekt")

    # 👉 HIER gebeurt nog exact hetzelfde als vroeger in /ask
    result = await handle_chat_request(
        question=question,
        session_id=session_id,
        language=language,
        raw_payload=data,
    )

    return JSONResponse(result)
