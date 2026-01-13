from fastapi import APIRouter, Request, HTTPException
from app.db.auth import get_auth_user_from_session

router = APIRouter()

@router.post("/ask/user")
async def ask_user(request: Request):
    # straks hier DB & conversation logic
    return {"error": "User chat not yet enabled"}
