from fastapi import APIRouter, HTTPException
from app.db.connection import get_db_conn

router = APIRouter()


@router.get("/chat/history")
async def chat_history(session_id: str):
    """
    Haalt chatgeschiedenis op op basis van chat-session.
    Auth is hier NIET leidend – alleen chat-continuïteit.
    """

    conn = get_db_conn()
    cur = conn.cursor()

    # -----------------------------
    # 1. Zorg voor stabiele chat-user
    # -----------------------------
    cur.execute(
        """
        SELECT id
        FROM users
        WHERE session_id = %s
        """,
        (session_id,),
    )
    row = cur.fetchone()

    if row:
        owner_id = row[0]
    else:
        cur.execute(
            """
            INSERT INTO users (session_id)
            VALUES (%s)
            RETURNING id
            """,
            (session_id,),
        )
        owner_id = cur.fetchone()[0]
        conn.commit()

    # -----------------------------
    # 2. Zorg voor EXACT één conversation per user
    # -----------------------------
    cur.execute(
        """
        SELECT id
        FROM conversations
        WHERE owner_id = %s
        """,
        (owner_id,),
    )
    row = cur.fetchone()

    if row:
        conversation_id = row[0]
    else:
        cur.execute(
            """
            INSERT INTO conversations (owner_id)
            VALUES (%s)
            RETURNING id
            """,
            (owner_id,),
        )
        conversation_id = cur.fetchone()[0]
        conn.commit()

    # -----------------------------
    # 3. Haal messages op (stabiel)
    # -----------------------------
    cur.execute(
        """
        SELECT role, content
        FROM messages
        WHERE conversation_id = %s
        ORDER BY created_at ASC
        """,
        (conversation_id,),
    )

    rows = cur.fetchall()
    conn.close()

    messages = [
        {"role": r[0], "content": r[1]}
        for r in rows
        if r[1]
    ]

    return {"messages": messages}
