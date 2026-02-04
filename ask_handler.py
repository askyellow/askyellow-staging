from fastapi import APIRouter, Request, HTTPException

from db import get_db_conn
from chat_shared import get_auth_user_from_session
from intent import detect_intent
from core.time_context import build_time_context
from chat_shared import store_message_pair
from category import detect_category
from specificity import detect_specificity
from search_questions import get_search_questions
from search_followup import interpret_search_followup
from websearch import tool_websearch
from app.services.affiliate_search import do_affiliate_search

router = APIRouter()
time_context = build_time_context()

# =============================================================
# ASK ENDPOINT
# =============================================================

@router.post("/ask")
async def ask(request: Request):
    payload = await request.json()

    question = (payload.get("question") or "").strip()
    session_id = payload.get("session_id")
    language = payload.get("language", "nl")

    prev_context = payload.get("meta", {}).get("search_context", {})
    prev_category = prev_context.get("category")
    prev_history = prev_context.get("history", [])

    if not question:
        raise HTTPException(status_code=400, detail="Missing question")

    # -----------------------------
    # AUTH
    # -----------------------------
    conn = get_db_conn()
    user = get_auth_user_from_session(conn, session_id)
    conn.close()

    # -----------------------------
    # INTENT
    # -----------------------------
    intent = detect_intent(question)
    mode = "search" if intent == "product" else "chat"

    category = detect_category(question)
    specificity = detect_specificity(question)

    # 🔑 CATEGORY PLAKKEN AAN LOPENDE SEARCH
    if mode == "search" and category is None and prev_category:
        category = prev_category

    # 🔑 OPTELSOM MAKEN
    history = prev_history + [question]
    search_query = " ".join(history)
    web_results = await tool_websearch(search_query)
    affiliate_results = await do_affiliate_search(search_query)


    # -----------------------------
    # TIME SHORTCUT
    # -----------------------------
    if _is_time_question(question):
        answer = f"Vandaag is het {TIME_CONTEXT.today_string()}."
        store_message_pair(session_id, question, answer)
        return _response(
            type_="text",
            answer=answer,
            intent=intent
        )

    # -----------------------------
    # MODE SELECT (voorbereid)
    # -----------------------------
    mode = payload.get("mode")
    if not mode:
        mode = "search" if intent == "product" else "chat"

    # ----------------------------------
    # SEARCH FLOW
    # ----------------------------------
    if mode == "search":

        # 1️⃣ Geen categorie
        if category is None:
            answer = (
                "Ik kan je helpen bij het kiezen 😊 "
                "Kun je aangeven waar je het product voor wilt gebruiken "
                "of waar je op wilt letten?"
            )

        # 2️⃣ Lage specificiteit
        elif specificity == "low":
            questions = get_search_questions(category)
            answer = " ".join(questions[:2])

        # 3️⃣ Hoge specificiteit
        elif specificity == "high":
            followup = interpret_search_followup(question)

            if followup == "accept":
                answer = "Top! Dan laat ik deze opties voor je staan 👍"
            elif followup == "refine":
                answer = "Helder 🙂 Ik ga verder zoeken met je voorkeuren."
            else:
                answer = (
                    "Helder! Ik ga nu zoeken met alles wat je tot nu toe hebt aangegeven 👍"
                )

        # 4️⃣ 🔒 VEILIGE FALLBACK (DIT ONTBRAK)
        else:
            answer = (
                "Helder, ik kijk even verder met wat je hebt aangegeven 👍"
            )

        store_message_pair(session_id, question, answer)

        return _response(
            type_="search",
            answer=answer,
            intent=intent,
            mode=mode,
            meta={
                "search_context": {
                    "category": category,
                    "history": history
                }
            }
        )

    # =============================================================
    # 💬 TEXT (FALLBACK)
    # =============================================================
    conn = get_db_conn()
    _, history = get_history_for_model(conn, session_id)
    conn.close()

    from search.web_context import build_web_context

    web_results = run_websearch_internal(question)
    web_context = build_web_context(web_results)

    hints = {
        "time_context": time_context,
        "web_context": web_context
    }

    if user and user.get("first_name"):
        hints["user_name"] = user["first_name"]

    final_answer, _ = call_yellowmind_llm(
        question=question,
        language=language,
        kb_answer=None,
        sql_match=None,
        hints=hints,
        history=history
    )

    if not final_answer:
        final_answer = "⚠️ Ik kreeg geen inhoudelijk antwoord terug, maar de chat werkt wel 🙂"

    store_message_pair(session_id, question, final_answer)

    return {
        "type": "text",
        "answer": final_answer
    }


# =============================================================
# HELPERS
# =============================================================

def _is_time_question(question: str) -> bool:
    TIME_KEYWORDS = [
        "vandaag",
        "welke dag is het",
        "wat voor dag is het",
        "laatste jaarwisseling",
        "afgelopen jaarwisseling",
    ]
    q = question.lower()
    return any(k in q for k in TIME_KEYWORDS)


def _response(type_, answer, intent=None, mode=None, meta=None):
    response = {
        "type": type_,
        "answer": answer,
        "intent": intent,
        "mode": mode,
    }

    if meta:
        response["meta"] = meta

    return response

