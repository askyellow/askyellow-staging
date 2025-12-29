from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
import secrets
import time
import traceback

from app.core.config import client
from app.knowledge_engine import (
    match_question,
    KNOWLEDGE_ENTRIES,
)
from app.identity_origin import try_identity_origin_answer
from app.chat_engine.utils import (
    search_sql_knowledge,
    wants_image,
    detect_cold_start,
)
from app.chat_engine.history import get_history_for_model
from app.chat_engine.llm import call_yellowmind_llm

from app.db.models import (
    get_or_create_user,
    get_or_create_conversation,
    save_message,
)

router = APIRouter()


# =============================================================
# MAIN ASK ENDPOINT
# =============================================================

@router.post("/ask")
async def ask_ai(request: Request):
    try:
        data = await request.json()

        question = (data.get("question") or "").strip()
        language = (data.get("language") or "nl").lower()

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
        # IMAGE ROUTE
        # -----------------------------
        if wants_image(question):
            try:
                img = client.images.generate(
                    model="gpt-image-1",
                    prompt=question,
                    size="1024x1024",
                )
                return {
                    "type": "image",
                    "url": img.data[0].url,
                    "prompt": question
                }
            except Exception as e:
                return {
                    "type": "error",
                    "error": str(e)
                }

        # -----------------------------
        # CONTEXT & KNOWLEDGE
        # -----------------------------
        identity_answer = try_identity_origin_answer(question, language)
        sql_match = search_sql_knowledge(question)

        try:
            kb_answer = match_question(question, KNOWLEDGE_ENTRIES)
        except Exception:
            kb_answer = None

        hints = {}

        # =============================================================
        # 🔍 SEARCH INTENT DETECTION
        # =============================================================
        SEARCH_TRIGGERS = [
            "opzoeken",
            "op zoek",
            "meest verkocht",
            "dit jaar",
            "dit moment",
            "actueel",
            "nu populair",
            "trending",
            "beste",
            "vergelijk",
            "waar koop",
            "waar kan ik",
        ]

        q_lower = question.lower()
        if any(trigger in q_lower for trigger in SEARCH_TRIGGERS):
            return {
                "type": "search",
                "query": question
            }

        # =============================================================
        # 🔥 HISTORY OPHALEN
        # =============================================================
        conn = get_db_conn()
        conv_id, history = get_history_for_model(conn, session_id)
        conn.close()

        # =============================================================
        # 🔥 LLM CALL (MET HISTORY)
        # =============================================================
        start_ai = time.time()

        final_answer, raw_output = call_yellowmind_llm(
            question=question,
            language=language,
            kb_answer=kb_answer,
            sql_match=sql_match,
            hints=hints,
            history=history
        )

        ai_ms = int((time.time() - start_ai) * 1000)

        if not final_answer:
            final_answer = "⚠️ Geen geldig antwoord beschikbaar."

        # =============================================================
        # OPSLAAN
        # =============================================================
        try:
            conn = get_db_conn()
            save_message(conn, conv_id, "user", question)
            save_message(conn, conv_id, "assistant", final_answer)
            conn.commit()
            conn.close()
        except Exception as e:
            print("⚠️ Chat history save failed:", e)

        status = detect_cold_start(0, 0, ai_ms, ai_ms)
        print(f"[STATUS] {status} | AI {ai_ms} ms")

        return {
            "answer": final_answer,
            "output": raw_output,
            "source": "yellowmind_llm"
        }

    except Exception as e:
        print("🔥 ASK ENDPOINT CRASH 🔥")
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"}
        )