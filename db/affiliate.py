from fastapi import APIRouter, Query
import pymysql

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


def get_affiliate_conn():
    return pymysql.connect(
        host="localhost",          # of Strato host
        user="dbu134629",
        password="AskYellow_20_25",
        database="askyellow_affiliate",
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor
    )
def get_affiliate_options(intent: str, query: str, limit: int = 3):
    if intent != "product":
        return []

    words = [w.lower() for w in query.split() if len(w) > 3]

    if not words:
        return []

    conn = get_affiliate_conn()
    try:
        with conn.cursor() as cur:
            conditions = " OR ".join(["keywords LIKE %s"] * len(words))
            params = [f"%{w}%" for w in words]

            sql = f"""
                SELECT
                    title,
                    dummy_url
                FROM affiliate_links
                WHERE active = 1
                  AND intent_type = 'product'
                  AND ({conditions})
                ORDER BY priority ASC
                LIMIT %s
            """

            cur.execute(sql, params + [limit])
            return cur.fetchall()

    finally:
        conn.close()
