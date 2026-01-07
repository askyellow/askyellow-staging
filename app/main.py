from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.history import router as history_router

from app.core.lifespan import lifespan
from app.core.config import (
    APP_ENV,
    APP_VERSION,
    DEBUG_MODE,
)

from app.routes.routes import router as main_router
from app.routes.ask import router as ask_router

from app.core.startup import on_startup
from app.routes import tools


app = FastAPI(
    title="AskYellow API",
    version=APP_VERSION,
)

# -------------------------------------------------
# ROUTES
# -------------------------------------------------

app.include_router(main_router)
app.include_router(ask_router)
app.include_router(tools.router, prefix="/tool")
app.include_router(history_router)

# -------------------------------------------------
# MIDDLEWARE
# -------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://askyellow.nl",
        "https://www.askyellow.nl",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



