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

        conversation_id = data.get("conversation_id")
        question = (data.get("question") or "").strip()
        language = (data.get("language") or "nl").lower()
        mode = (data.get("mode") or "chat").lower()

        if not conversation_id:
            return JSONResponse(
                status_code=400,
                content={"error": "conversation_id ontbreekt"}
            )

        conversation_id = int(conversation_id)

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
        history = load_history_for_llm(conversation_id)

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

        # -----------------------------
        # Opslaan in NIEUWE structuur
        # -----------------------------
        conn = get_db_conn()
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO messages (conversation_id, role, content)
            VALUES (%s, %s, %s)
            """,
            (conversation_id, "user", question)
        )

        cur.execute(
            """
            INSERT INTO messages (conversation_id, role, content)
            VALUES (%s, %s, %s)
            """,
            (conversation_id, "assistant", final_answer)
        )

        cur.execute(
            """
            UPDATE conversations
            SET last_message_at = NOW()
            WHERE id = %s
            """,
            (conversation_id,)
        )

        conn.commit()
        conn.close()

        # -----------------------------
        # Response
        # -----------------------------
        return {
            "answer": final_answer,
            "source": "yellowmind_llm",
        }

    except Exception:
        print("ASK ENDPOINT CRASH")
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"}
        )
