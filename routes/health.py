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
