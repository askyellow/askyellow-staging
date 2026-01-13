# knowledge/routes.py
from fastapi import APIRouter

router = APIRouter()

@router.get("/candidates")
def list_candidates():
    return {"status": "ok", "items": []}
