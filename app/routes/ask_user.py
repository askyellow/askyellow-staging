from fastapi import APIRouter, Request, HTTPException
from app.auth import require_auth_session

router = APIRouter()

@router.post("/ask/user")
async def ask_user(request: Request):
    # straks hier DB & conversation logic
    return {"error": "User chat not yet enabled"}
