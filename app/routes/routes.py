from fastapi import APIRouter
from app.routes.health import router as health_router
from app.routes.ask import router as ask_router
from app.routes.auth import router as auth_router
from app.routes.tools import router as tools_router

router = APIRouter()

router.include_router(health_router)
router.include_router(ask_router)
router.include_router(auth_router)
router.include_router(tools_router)
