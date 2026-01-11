from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import secrets
import time
import traceback

from app.services.detect import (
    detect_image_intent,
    detect_search_intent,
    detect_hints,
    log_ai_status,
)
from app.services.image import generate_image
from app.services.history_service import (
    load_history_for_llm,
    persist_user_message,
    persist_ai_message,
)
from app.chat_engine.llm import run_llm
from app.services.context import build_context

router = APIRouter()

def build_frontend_messages(history, question, final_answer):
    messages = []

    for msg in history:
        r = msg.get("role")
        c = msg.get("content")

        if r == "assistant":
            r = "ai"

        messages.append({
            "role": r,
            "content": c
        })

    messages.append({
        "role": "user",
        "content": question
    })

    messages.append({
        "role": "ai",
        "content": final_answer
    })

    return messages

# =============================================================
# MAIN ASK ENDPOINT
# =============================================================


@router.post("/ask")
async def ask_ai(request: Request):
    try:
        data = await request.json()

        question = (data.get("question") or "").strip()
        language = (data.get("language") or "nl").lower()
        mode = (data.get("mode") or "chat").lower()

        # -----------------------------
        # User-mode: koppel user_id aan session_id
        # -----------------------------
        if mode == "user":
            session_id = (
                data.get("user_id")
                or data.get("userId")
                or data.get("uid")
            or ""
        )

        # -----------------------------
        # Session ID bepalen
        # -----------------------------
        session_id = (
            data.get("session_id")
            or data.get("sessionId")
            or data.get("session")
            or data.get("sid")
            or ""
        )
        session_id = str(session_id).strip()
        if not session_id:
            session_id = "anon-" + secrets.token_hex(8)

        if not question:
            return JSONResponse(
                status_code=400,
                content={"error": "Geen vraag ontvangen."}
            )

        # -----------------------------
        # Intent detectie
        # -----------------------------
        hints = detect_hints(question)

        if detect_image_intent(question):
            return generate_image(question)

        if detect_search_intent(question):
            return {
                "type": "search",
                "query": question,
            }

        # -----------------------------
        # Context & history
        # -----------------------------
        context = build_context(question, language)
        history = load_history_for_llm(session_id)

        persist_user_message(session_id, question)

        
        # -----------------------------
        # LLM call
        # -----------------------------
        start_ai = time.time()

        final_answer, raw_output = run_llm(
            question=question,
            language=language,
            kb_answer=context["kb_answer"],
            sql_match=context["sql_match"],
            hints=hints,
            history=history,
            mode=mode,
        )

        ai_ms = int((time.time() - start_ai) * 1000)
        log_ai_status(ai_ms)

        persist_ai_message(session_id, final_answer)

        
        # ----------------------------
        # Build messages for frontend
        # ----------------------------
        messages_for_frontend = build_frontend_messages(
        history,
        question,
        final_answer
        )



        # -----------------------------
        # Response
        # -----------------------------
        return {
            "answer": final_answer,
            "messages": messages_for_frontend,
            "source": "yellowmind_llm",
        }


    except Exception:
        print("ASK ENDPOINT CRASH")
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"}
        )
