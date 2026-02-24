from fastapi import APIRouter
from search_v2.analyzer import ai_analyze_input
from search_v2.analyzer import ai_generate_refinement_question
from search_v2.analyzer import ai_generate_targeted_question
from search_v2.query_builder import ai_build_search_decision
from search_v2.state import get_conversation, add_message
from search_v2.search_log_service import log_search_to_db
from psycopg2.extras import Json
from db import get_db_conn
import traceback
from fastapi.responses import HTMLResponse
from html import escape
from category import detect_category
from category import normalize_category


router = APIRouter(prefix="/search_v2", tags=["search_v2"])

from search_v2.state import get_or_create_state, merge_analysis_into_state

from search_v2.query_builder import ai_build_search_decision
from search_v2.state import get_conversation, add_message



def ai_generate_advice(conversation: list[dict]) -> str:
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Je bent een deskundige, eerlijke verkoopmedewerker. "
                    "Geef helder en praktisch advies. "
                    "Leg kort uit waarom iets geschikt is. "
                    "Geen verkooppraat. Geen productlinks."
                )
            },
            *conversation  # volledige dialoog
        ],
        temperature=0.3
    )

    return response.choices[0].message.content.strip()

@router.post("/analyze")
async def analyze_v2(data: dict):
    session_id = data.get("session_id", "demo")
    query = (data.get("query") or "").strip()

    # 1️⃣ User message opslaan
    add_message(session_id, "user", query)

    # 2️⃣ Conversatie ophalen
    conversation = get_conversation(session_id)

    # 3️⃣ AI beslissing laten maken
    decision = ai_build_search_decision(conversation)

        # 🔥 AI → STATE SYNC
    state = get_or_create_state(session_id)

    ai_category = decision.get("analysis", {}).get("category")
    category = normalize_category(ai_category)

    if not category:
        # laatste redmiddel
        category = detect_category(query)

    if category:
        state["category"] = category

    # refinement guard
    category = state.get("category")
    refinement_depth = len([m for m in conversation if m["role"] == "assistant"])

    MIN_REFINEMENTS = {
        "beeld_en_geluid": 2,
        "sport": 3,
        "huishouden": 2,
    }

    required = MIN_REFINEMENTS.get(category, 1)

    if decision["response_mode"] == "search" and refinement_depth < required:
        decision["response_mode"] = "ask"
        decision["clarification_question"] = ai_generate_refinement_question(state)
    
    # 4️⃣ Nog niet klaar → vraag stellen
    if not decision["is_ready_to_search"]:
        add_message(session_id, "assistant", decision["clarification_question"])
        return {
            "action": "ask",
            "question": decision["clarification_question"],
            "confidence": decision["confidence"]
        }

    # 5️⃣ Adviesmodus
    if decision["response_mode"] == "advice":
        advice_text = ai_generate_advice(conversation)
        add_message(session_id, "assistant", advice_text)

        return {
            "action": "advice",
            "answer": advice_text,
            "confidence": decision["confidence"]
        }

    # 6️⃣ Zoekmodus
    if decision["response_mode"] == "search":
        add_message(session_id, "assistant", decision["proposed_query"])

         # ==============================
    # 🗄 SEARCH V2 LOGGING
    # ==============================
        try:
            conn = get_db_conn()
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO search_logs
                (
                    session_id,
                    user_input,
                    mode,
                    intent,
                    constraints_json,
                    steps,
                    pending_key,
                    results_count
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                session_id,
                query,
                "search_v2",
                decision.get("intent"),
                Json(decision),
                len(conversation),
                None,
                None
            ))

            row = cur.fetchone()
            inserted_id = row["id"]            
            conn.commit()
            cur.close()
            conn.close()

            print(f"[SEARCH_V2 LOGGED] ID={inserted_id}")

        except Exception as e:
            print("[SEARCH_V2 LOGGING FAILED]", e)
            print(traceback.format_exc())

    return {
        "action": "search",
        "query": decision["proposed_query"],
        "confidence": decision["confidence"]
    }

def should_refine(state):
    if state.get("refinement_done"):
        return False

    if state.get("intent") not in ["search", "search_product"]:
        return False

    if not state.get("category"):
        return False

    if state["constraints"].get("price_max") is None:
        return False

    return True

@router.get("/admin", response_class=HTMLResponse)
def admin_search_v2():
    conn = get_db_conn()
    cur = conn.cursor()  # bij RealDictCursor werkt fetchall() met dict rows, anders tuples

    # Sessies + aantal berichten + laatste activiteit
    cur.execute("""
        SELECT session_id,
               COUNT(*) AS msg_count,
               MAX(created_at) AS last_seen
        FROM search_v2_messages
        GROUP BY session_id
        ORDER BY last_seen DESC
        LIMIT 200
    """)
    rows = cur.fetchall()

    cur.close()
    conn.close()

    # Helper: pak values uit tuple of dict (want jouw cursor kan dicts geven)
    def getv(r, k, idx):
        return r[k] if isinstance(r, dict) else r[idx]

    items_html = []
    for r in rows:
        session_id = getv(r, "session_id", 0)
        msg_count = getv(r, "msg_count", 1)
        last_seen = getv(r, "last_seen", 2)

        items_html.append(
            f"""
            <tr>
              <td><a href="/search_v2/admin/session/{escape(str(session_id))}">{escape(str(session_id))}</a></td>
              <td>{msg_count}</td>
              <td>{escape(str(last_seen))}</td>
            </tr>
            """
        )

    html = f"""
    <html>
    <head>
      <meta charset="utf-8" />
      <title>Search V2 Admin</title>
      <style>
        body {{ font-family: Arial, sans-serif; padding: 16px; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; }}
        th {{ background: #f5f5f5; text-align: left; }}
        a {{ text-decoration: none; }}
      </style>
    </head>
    <body>
      <h2>Search V2 Admin</h2>
      <p>Laatste 200 sessies</p>
      <table>
        <thead>
          <tr>
            <th>session_id</th>
            <th>messages</th>
            <th>last_seen</th>
          </tr>
        </thead>
        <tbody>
          {''.join(items_html) if items_html else '<tr><td colspan="3">Geen sessies gevonden.</td></tr>'}
        </tbody>
      </table>
    </body>
    </html>
    """
    return HTMLResponse(html)

@router.get("/admin/session/{session_id}", response_class=HTMLResponse)
def admin_search_v2_session(session_id: str):
    conn = get_db_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT message_order, role, content, created_at
        FROM search_v2_messages
        WHERE session_id = %s
        ORDER BY message_order ASC
    """, (session_id,))
    rows = cur.fetchall()

    cur.close()
    conn.close()

    def getv(r, k, idx):
        return r[k] if isinstance(r, dict) else r[idx]

    bubbles = []
    for r in rows:
        order_ = getv(r, "message_order", 0)
        role = getv(r, "role", 1)
        content = getv(r, "content", 2)
        created_at = getv(r, "created_at", 3)

        cls = "user" if role == "user" else "assistant"
        bubbles.append(
            f"""
            <div class="msg {cls}">
              <div class="meta">#{order_} · {escape(str(role))} · {escape(str(created_at))}</div>
              <div class="text">{escape(str(content)).replace('\\n','<br>')}</div>
            </div>
            """
        )

    html = f"""
    <html>
    <head>
      <meta charset="utf-8" />
      <title>Search V2 Session</title>
      <style>
        body {{ font-family: Arial, sans-serif; padding: 16px; }}
        .topbar {{ display: flex; gap: 12px; align-items: center; margin-bottom: 12px; }}
        .msg {{ border: 1px solid #ddd; border-radius: 10px; padding: 10px; margin: 8px 0; }}
        .msg.user {{ background: #fffbe6; }}
        .msg.assistant {{ background: #eef6ff; }}
        .meta {{ font-size: 12px; opacity: 0.7; margin-bottom: 6px; }}
        .text {{ white-space: normal; line-height: 1.35; }}
        a {{ text-decoration: none; }}
        .pill {{ padding: 4px 8px; border: 1px solid #ddd; border-radius: 999px; font-size: 12px; }}
      </style>
    </head>
    <body>
      <div class="topbar">
        <a href="/search_v2/admin">← terug</a>
        <span class="pill">session_id: {escape(session_id)}</span>
        <span class="pill">messages: {len(rows)}</span>
      </div>

      <h2>Conversatie</h2>
      {''.join(bubbles) if bubbles else '<p>Geen berichten gevonden voor deze session_id.</p>'}
    </body>
    </html>
    """
    return HTMLResponse(html)