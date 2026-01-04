from fastapi import APIRouter
from app.core.config import APP_ENV, APP_VERSION

router = APIRouter()

@router.get("/health")
def health():
    return {
        "status": "ok",
        "env": APP_ENV,
        "version": APP_VERSION,
    }


@app.get("/health")
def health():
    """Eenvoudige healthcheck met DB-status en environment-info."""
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