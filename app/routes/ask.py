from fastapi import APIRouter, Request
from app.chat_engine.routes import router as chat_engine_router

router = APIRouter()
router.include_router(chat_engine_router)
