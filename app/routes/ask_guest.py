from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import time

router = APIRouter()

@router.post("/ask/guest")
async def ask_guest(request: Request):
    try:
        data = await request.json()
        question = (data.get("question") or "").strip()
        if not question:
            return JSONResponse(status_code=400, content={"error": "Geen vraag"})

        # 🔹 Tijdelijk dummy-antwoord (vervang straks door echte LLM)
        time.sleep(0.2)
        answer = f"(gast) Je vroeg: {question}"

        return {"answer": answer}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Guest error"})
