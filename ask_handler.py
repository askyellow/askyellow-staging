from fastapi import APIRouter, Request, HTTPException

from db import get_db_conn
from chat_shared import get_auth_user_from_session, store_message_pair
from intent import detect_intent
from core.time_context import build_time_context

from category import detect_category
from specificity import detect_specificity
from search_questions import get_search_questions
from search_followup import interpret_search_followup

from websearch import do_websearch
from affiliate_search import do_affiliate_search
from llm import call_yellowmind_llm
from affiliate_mock import load_mock_affiliate_products

import logging

logger = logging.getLogger(__name__)

router = APIRouter()
time_context = build_time_context()
logging.basicConfig(level=logging.INFO)

# =============================================================
# ASK ENDPOINT
# =============================================================
logger.warning("🔥 ASK_HANDLER VERSION XYZ LOADED 🔥")

@router.post("/ask")
async def ask(request: Request):
    payload = await request.json()

    
    # ---------------------------------------------------------
    # BASIC INPUT
    # ---------------------------------------------------------
    question = (payload.get("question") or "").strip()
    session_id = payload.get("session_id")
    language = payload.get("language", "nl")
    mode = payload.get("mode")  # frontend mag dit sturen
    search_ready = payload.get("search_ready", False)
    # 🔑 tijdelijke search state (per sessie)

    if not question:
        raise HTTPException(status_code=400, detail="Missing question")


    # ---------------------------------------------------------
    # AUTH (chat-only relevant, maar licht genoeg om altijd te doen)
    # ---------------------------------------------------------
    conn = get_db_conn()
    user = get_auth_user_from_session(conn, session_id)
    conn.close()

    # ---------------------------------------------------------
    # INTENT / MODE ROUTING
    # ---------------------------------------------------------
    intent = detect_intent(question)

    if not mode:
        mode = "search" if intent == "product" else "chat"

        logger.info(
    "[ASK] incoming",
    extra={
        "session_id": session_id,
        "mode": mode,
        "intent": intent
    }
    )
    # ---------------------------------------------------------
    # TIME SHORTCUT (globaal, los van search/chat)
    # ---------------------------------------------------------
    if _is_time_question(question):
        answer = f"Vandaag is het {time_context.today_string()}."
        store_message_pair(session_id, question, answer)
        return _response(
            type_="text",
            answer=answer,
            intent=intent,
            mode=mode
        )

   
    # =========================================================
    # 🔍 SEARCH FLOW
    # =========================================================
    if mode == "search":

        search_state = get_search_state(session_id)
        constraints = search_state["constraints"]

        # 1️⃣ laad producten 1x
        if search_state["products"] is None:
            search_state["products"] = load_mock_affiliate_products(
                search_query=question
            )

        logger.info(
            "[SEARCH] state",
            extra={
                "session_id": session_id,
                "question": question,
                "constraints": constraints,
                "steps": search_state["steps"],
                "products": len(search_state["products"])
            }
        )

        # 2️⃣ verwerk nieuw antwoord → constraint
        new_constraint = extract_constraint_from_answer(
            question,
            search_state.get("pending_key")
        )
        if new_constraint:
            constraints.update(new_constraint)
            search_state["steps"] += 1

            logger.info(
                "[SEARCH] constraint check",
                extra={
                    "question": question,
                    "new_constraint": new_constraint,
                    "steps": search_state["steps"]
                }
            )


        # 3️⃣ reduceer ALTIJD
        filtered_products = apply_constraints(
            search_state["products"],
            constraints
        )
        search_state["products"] = filtered_products

        logger.info(
            "[SEARCH] reduced",
            extra={
                "session_id": session_id,
                "remaining": len(filtered_products),
                "constraints": constraints
            }
        )

        affiliate_results = None

        # 4️⃣ beslis: doorvragen of afronden
        if search_state["steps"] >= 2 and len(filtered_products) <= 10:
            answer = "Ik heb een paar goede opties voor je gevonden 👇"
            affiliate_results = filtered_products[:3]
        else:
            answer = ai_search_followup(
                user_input=question,
                search_query=question
            )
            search_state["pending_key"] = "type"

        store_message_pair(session_id, question, answer)

        payload = {
            "type_": "search",
            "answer": answer,
            "intent": intent,
            "mode": "search"
        }

        payload["affiliate_results"] = (
            affiliate_results
            or search_state["products"][:3]
        )


        return _response(**payload)

    # =========================================================
    # 💬 CHAT FALLBACK (ONGEWIIJZIGD)
    # =========================================================
    conn = get_db_conn()
    _, history = get_history_for_model(conn, session_id)
    conn.close()

    from search.web_context import build_web_context
    from websearch import do_websearch as run_websearch_internal
    from yellowmind import call_yellowmind_llm

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
        "type_": "text",
        "answer": final_answer
    }


# =============================================================
# HELPERS
# =============================================================

def normalize_answer(answer: str):
    a = answer.lower()

    if a in ("ja", "yes"):
        return True
    if a in ("nee", "no"):
        return False

    # getallen
    import re
    m = re.search(r"\d+", a)
    if m:
        return int(m.group())

    return a.strip()

def apply_constraints(products: list, constraints: dict) -> list:
    if not constraints:
        return products

    results = products

    for key, value in constraints.items():

        if key == "price_max":
            results = [
                p for p in results
                if p.get("price", 999999) <= value
            ]
            continue
        
        def matches(p):
            # 1️⃣ facets (toekomst)
            facets = p.get("facets")
            if isinstance(facets, dict) and key in facets:
                return facets[key] == value

            # 2️⃣ top-level (huidige mock)
            if key in p:
                return p[key] == value

            # 3️⃣ onbekende key → product blijft (niet uitsluiten)
            return True

        results = [p for p in results if matches(p)]

    return results


def extract_constraint_from_answer(answer: str, pending_key: str):
    if not pending_key or not answer:
        return None


    value = normalize_answer(answer)

    return {pending_key: value}



SEARCH_STATE = {}

def get_search_state(session_id):
    if session_id not in SEARCH_STATE:
        SEARCH_STATE[session_id] = {
            "constraints": {},
            "products": None,
            "steps": 0,
            "pending_key": None
        }
    return SEARCH_STATE[session_id]

def reduce_products(products, constraints):
    results = products

    for key, value in constraints.items():
        results = [
            p for p in results
            if p.get("facets", {}).get(key) == value
        ]

    return results

def filter_products_by_query(products, query: str):
    q = query.lower().split()

    results = []
    for p in products:
        attrs = p.get("attributes", {})
        match_count = sum(
            1 for v in attrs.values()
            if str(v).lower() in q
        )
        if match_count > 0:
            results.append(p)

    return results

def apply_faceted_filters(products: list, filters: dict) -> list:
    if not filters:
        return products

    results = products

    for key, value in filters.items():
        # max / min ranges
        if key.endswith("_max"):
            base = key.replace("_max", "")
            results = [
                p for p in results
                if p.get("facets", {}).get(base) is not None
                and p["facets"][base] <= value
            ]

        elif key.endswith("_min"):
            base = key.replace("_min", "")
            results = [
                p for p in results
                if p.get("facets", {}).get(base) is not None
                and p["facets"][base] >= value
            ]

        # exact match
        else:
            results = [
                p for p in results
                if p.get("facets", {}).get(key) == value
            ]

    return results

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


def _response(type_, answer, intent=None, mode=None, meta=None, affiliate_results=None):
    response = {
        "type_": type_,
        "answer": answer,
        "intent": intent,
        "mode": mode,
    }

    if meta:
        response["meta"] = meta

    if affiliate_results:
        response["affiliate_results"] = affiliate_results

    return response



def detect_category(query: str) -> str:
    q = query.lower()

    if any(w in q for w in ["kopen", "prijs", "goedkoop", "beste"]):
        return "product"

    if any(w in q for w in ["hoe", "wat is", "uitleg"]):
        return "info"

    return "general"

def detect_specificity(query: str) -> str:
    length = len(query.split())

    if length <= 2:
        return "low"
    if length <= 5:
        return "medium"
    return "high"

def ai_search_followup(user_input: str, search_query: str) -> str:
    prompt = f"""
Je bent YellowMind, een behulpzame maar nuchtere zoekassistent.

Dit is een vervolgstap in dezelfde productzoektocht.
De gebruiker bouwt zijn zoekvraag stap voor stap op.

Huidige zoekcontext (samengevat):
"{search_query}"

Laatste antwoord van de gebruiker:
"{user_input}"

Je taak:
- Stel EXACT 1 korte, natuurlijke vervolgvraag
- Ga logisch verder op basis van de zoekcontext
- Gebruik wat de gebruiker al heeft aangegeven (zoals budget, gebruik, voorkeuren)
- Vraag NIET opnieuw naar iets dat al duidelijk is
- Geen lijstjes
- Geen uitleg
- Geen begroeting of afsluiting

Geef alleen de vervolgvraag.
""".strip()

    answer, _ = call_yellowmind_llm(
        question=prompt,
        language="nl",
        kb_answer=None,
        sql_match=None,
        history=[],
        hints={"mode": "search_followup"},
    )

    return (answer or "").strip()
