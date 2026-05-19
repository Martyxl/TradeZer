import os
import structlog
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.db.base import Base
from app.db.engine import engine
from app.db.session import session_context
from app.jobs.scheduler import start_scheduler, stop_scheduler
from app.routers import (
    tickers_router,
    news_router,
    summary_router,
    admin_router,
    history_router,
    stream_router,
    stats_router,
)

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer() if settings.app_env == "development" else structlog.processors.JSONRenderer(),
    ]
)

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Tradezer starting", env=settings.app_env)
    settings.check_missing_keys()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Auto-seed: pokud je DB prázdná (žádné tickery), spusť seed automaticky
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT COUNT(*) FROM tickers"))
        ticker_count = result.scalar()

    if ticker_count == 0:
        log.info("DB is empty, running auto-seed")
        from app.db.seed import seed
        async with session_context() as session:
            await seed(session)
        log.info("Auto-seed complete")

    # APScheduler nefunguje na Vercel serverless (stateless funkce bez persistent procesu).
    # Na Vercelu použij Cron Jobs: POST /api/refresh každých N minut.
    if settings.app_env != "test" and not os.environ.get("VERCEL"):
        start_scheduler()

    yield

    stop_scheduler()
    await engine.dispose()
    log.info("Tradezer shutdown")


app = FastAPI(
    title="Tradezer — News Impact Trading Agent",
    version="1.0.0",
    lifespan=lifespan,
)

_cors_origins = ["http://localhost:3000", "https://*.vercel.app"]
if os.environ.get("ALLOWED_ORIGIN"):
    _cors_origins.append(os.environ["ALLOWED_ORIGIN"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tickers_router)
app.include_router(news_router)
app.include_router(summary_router)
app.include_router(admin_router)
app.include_router(history_router)
app.include_router(stream_router)
app.include_router(stats_router)


@app.get("/")
async def root():
    return {"app": "Tradezer", "version": "1.0.0", "docs": "/docs"}
