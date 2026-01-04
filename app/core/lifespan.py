from contextlib import asynccontextmanager
from app.core.startup import on_startup

@asynccontextmanager
async def lifespan(app):
    print("🔥 LIFESPAN START")
    on_startup()
    print("🔥 LIFESPAN BEFORE YIELD")
    yield
    print("🔥 LIFESPAN SHUTDOWN")

