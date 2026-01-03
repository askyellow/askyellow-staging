from contextlib import asynccontextmanager
from app.core.startup import on_startup

@asynccontextmanager
async def lifespan(app):
    # ⏳ startup
    on_startup()
    yield
    # 🧹 shutdown (later, indien nodig)
