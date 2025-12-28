from fastapi import APIRouter
from app.chat_engine.auth import router as auth_router

router = APIRouter()
router.include_router(auth_router)
