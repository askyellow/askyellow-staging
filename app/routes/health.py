from fastapi import APIRouter
from app.core.config import APP_ENV, APP_VERSION
from app.db.connection import get_db_conn

router = APIRouter()

@router.get("/health")
def health():
    db_ok = True
    try:
        db = get_db_conn()
        cur = db.cursor()
        cur.execute("SELECT 1")
        cur.close()
        db.close()
    except Exception:
        db_ok = False

    return {
        "status": "ok",
        "env": APP_ENV,
        "version": APP_VERSION,
        "db_ok": db_ok,
    }
