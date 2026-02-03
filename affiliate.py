from fastapi import APIRouter, Query
import pymysql
from db import get_db_conn


router = APIRouter()

@router.get("/affiliate/options")
def affiliate_options(
    q: str = Query(...),
    intent: str = Query("unknown")
):
    options = get_affiliate_options(intent=intent, query=q)

    return {
        "count": len(options),
        "options": options
    }


def get_affiliate_options(intent: str, query: str, limit: int = 3):
    if intent != "product":
        return []

    words = [w.lower() for w in query.split() if len(w) > 3]
    if not words:
        return []

    conditions = " OR ".join(["l.keywords ILIKE %s"] * len(words))
    params = [f"%{w}%" for w in words]

    sql = f"""
        SELECT
            l.title,
            l.url
        FROM affiliate_links l
        JOIN affiliate_partners p ON p.id = l.partner_id
        WHERE l.active = TRUE
          AND p.status = 'active'
          AND l.intent_type = 'product'
          AND ({conditions})
        ORDER BY l.priority ASC
        LIMIT %s
    """

    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params + [limit])
            rows = cur.fetchall()

            return [
            {
                "title": r["title"],
                "dummy_url": r["url"]
            }
            for r in rows
        ]

    finally:
        conn.close()

