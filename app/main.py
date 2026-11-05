import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from datetime import datetime

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.routes import router
from app.core.config import settings
from app.db import Base, SessionLocal, engine
from app.services.tournament import try_auto_start
from app.web import router as web_router
from app.feed import router as feed_router


def _auto_start_finale() -> None:
    with SessionLocal() as db:
        try_auto_start(db, datetime.now(settings.qualification_deadline.tzinfo))


async def _finale_auto_start_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(_auto_start_finale)
        except Exception:
            logging.getLogger(__name__).exception("Finale auto-start failed")
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auto_create_schema:
        Base.metadata.create_all(bind=engine)
    task = asyncio.create_task(_finale_auto_start_loop())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


app = FastAPI(
    title="Laddercompetitie API",
    version="0.1.0",
    description="API for the office ladder competition.",
    lifespan=lifespan,
)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    https_only=settings.session_https_only,
    same_site="lax",
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_host_list)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(router, prefix="/api")
app.include_router(web_router)
app.include_router(feed_router)
