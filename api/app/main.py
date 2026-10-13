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
    bias_router,
    valuation_router,
    tickers_router,
    news_router,
    summary_router,
    admin_router,
    history_router,
    stream_router,
    stats_router,
    auth_router,
    journal_router,
    discovery_router,
    gamma_router,
    regime_router,
    dashboard_router,
    smart_money_router,
    billing_router,
    investments_router,
    darkpool_router,
    fund_router,
)

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer() if settings.app_env == "development" else structlog.processors.JSONRenderer(),
    ]
)

log = structlog.get_logger(__name__)


import hashlib

# Postgres migrace (idempotentní ALTER … IF NOT EXISTS). PŘIDÁVEJ SEM NOVÉ — otisk schématu
# (`_schema_fingerprint`) se změní a příští start funkce je jednorázově provede.
_PG_MIGRATIONS: list[tuple[str, str]] = [
    ('price_series column',
     'ALTER TABLE market_reactions ADD COLUMN IF NOT EXISTS price_series JSONB'),
    ('daily_bias NY-path columns',
     'ALTER TABLE daily_bias ADD COLUMN IF NOT EXISTS ny_open_price DOUBLE PRECISION, ADD COLUMN IF NOT EXISTS ny_adverse_pct DOUBLE PRECISION, ADD COLUMN IF NOT EXISTS ny_adverse_min INTEGER, ADD COLUMN IF NOT EXISTS ny_favorable_pct DOUBLE PRECISION, ADD COLUMN IF NOT EXISTS entry_filled BOOLEAN, ADD COLUMN IF NOT EXISTS entry_pnl_pct DOUBLE PRECISION, ADD COLUMN IF NOT EXISTS entry_win BOOLEAN'),
    ('users login-tracking columns',
     'ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMP, ADD COLUMN IF NOT EXISTS login_count INTEGER NOT NULL DEFAULT 0, ADD COLUMN IF NOT EXISTS reset_requested BOOLEAN NOT NULL DEFAULT FALSE'),
    ('users Stripe billing columns',
     'ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(64), ADD COLUMN IF NOT EXISTS subscription_status VARCHAR(32), ADD COLUMN IF NOT EXISTS subscription_period_end TIMESTAMP'),
    ('investment_quotes 52w columns',
     'ALTER TABLE investment_quotes ADD COLUMN IF NOT EXISTS high_52w DOUBLE PRECISION, ADD COLUMN IF NOT EXISTS low_52w DOUBLE PRECISION'),
    ('val_instruments request_count',
     'ALTER TABLE val_instruments ADD COLUMN IF NOT EXISTS request_count INTEGER NOT NULL DEFAULT 0'),
    ('fund_snapshots benchmark',
     'ALTER TABLE fund_snapshots ADD COLUMN IF NOT EXISTS benchmark DOUBLE PRECISION'),
    ('journal_entries SL/TP/outcome',
     'ALTER TABLE journal_entries ADD COLUMN IF NOT EXISTS stop_price DOUBLE PRECISION, ADD COLUMN IF NOT EXISTS target_price DOUBLE PRECISION, ADD COLUMN IF NOT EXISTS outcome VARCHAR(10)'),
]


def _schema_fingerprint() -> str:
    """Otisk definice modelů + migrací. Beze změny kódu schématu je stejný → start funkce
    přeskočí create_all a všechny ALTERy (dřív je opakoval KAŽDÝ studený start = desítky dotazů)."""
    parts = [f"{t.name}.{c.name}:{c.type}" for t in Base.metadata.sorted_tables for c in t.columns]
    parts += [sql for _, sql in _PG_MIGRATIONS]
    return hashlib.sha1("|".join(sorted(parts)).encode()).hexdigest()


async def _startup_db() -> None:
    """DB init (create_all, migrace, seed, admin). Volané z lifespan v try/except,
    aby výpadek DB při startu neshodil celý backend (FUNCTION_INVOCATION_FAILED).
    Těžké DDL (create_all + ALTERy) běží jen když se změnil otisk schématu (Postgres)."""
    fp = _schema_fingerprint()
    async with engine.begin() as conn:
        stored = None
        if not settings.is_sqlite:
            await conn.execute(text(
                "CREATE TABLE IF NOT EXISTS app_schema_info (k VARCHAR(20) PRIMARY KEY, v VARCHAR(64) NOT NULL)"))
            stored = (await conn.execute(text("SELECT v FROM app_schema_info WHERE k = 'fingerprint'"))).scalar()
        if stored == fp:
            log.info("Schema fingerprint unchanged — DDL skipped")
        else:
            await conn.run_sync(Base.metadata.create_all)
            if not settings.is_sqlite:
                for name, sql in _PG_MIGRATIONS:
                    try:
                        async with conn.begin_nested():  # savepoint: selhání jedné migrace nezruší transakci
                            await conn.execute(text(sql))
                        log.info("Migration ensured", name=name)
                    except Exception as e:
                        log.warning("Migration skipped", name=name, error=str(e))
                await conn.execute(text(
                    "INSERT INTO app_schema_info (k, v) VALUES ('fingerprint', :v) "
                    "ON CONFLICT (k) DO UPDATE SET v = EXCLUDED.v"), {"v": fp})

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

    # Admin účet z env (NIKDY natvrdo v kódu — repo je veřejné). Nastav na Vercelu
    # ADMIN_USERNAME + ADMIN_PASSWORD; heslo se uloží hashované, jde změnit v účtu.
    admin_user = os.environ.get("ADMIN_USERNAME")
    admin_pass = os.environ.get("ADMIN_PASSWORD")
    if admin_user and admin_pass:
        from sqlalchemy import select
        from app.models import User
        from app.services.auth_service import hash_password
        async with session_context() as session:
            existing = await session.scalar(select(User).where(User.username == admin_user))
            if existing is None:
                session.add(User(username=admin_user, password_hash=hash_password(admin_pass),
                                 plan="pro", is_admin=True))
                await session.commit()
                log.info("Admin account seeded", username=admin_user)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Tradezer starting", env=settings.app_env)
    settings.check_missing_keys()
    try:
        await _startup_db()
    except Exception as e:  # noqa: BLE001
        # Výpadek DB při startu NESMÍ shodit celý backend — appka nabootuje degradovaně
        # (non-DB endpointy jedou, DB endpointy vrátí zachytitelnou chybu místo hard crashe).
        log.error("DB startup failed — booting in degraded mode", error=str(e))

    # APScheduler nefunguje na Vercel serverless (stateless funkce bez persistent procesu).
    # Na Vercelu použij Cron Jobs: POST /api/refresh každých N minut.
    if settings.app_env != "test" and not os.environ.get("VERCEL"):
        start_scheduler()

    yield

    stop_scheduler()
    await engine.dispose()
    log.info("Tradezer shutdown")


# V produkci skryj /docs, /redoc i /openapi.json — nemapovat útočníkovi admin API.
# Robustně: APP_ENV=production NEBO Vercel prostředí (kdyby APP_ENV nebylo nastavené).
_docs_off = settings.is_production or os.environ.get("VERCEL_ENV") == "production"
app = FastAPI(
    title="Tradezer — News Impact Trading Agent",
    version="1.2.0",
    lifespan=lifespan,
    docs_url=None if _docs_off else "/docs",
    redoc_url=None if _docs_off else "/redoc",
    openapi_url=None if _docs_off else "/openapi.json",
)

# CORS pinnutý na známé originy. Prod frontend jde přes Next.js rewrite (same-origin
# proxy), takže cross-origin sem chodí jen dev/preview. Wildcard '*.vercel.app' ve
# Starlette allow_origins NEfunguje (bere se literálně) → přes allow_origin_regex.
_cors_origins = ["http://localhost:3000"]
if os.environ.get("ALLOWED_ORIGIN"):
    _cors_origins.append(os.environ["ALLOWED_ORIGIN"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=r"https://[a-z0-9-]+\.vercel\.app",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Internal-Token", "Authorization"],
)

# CDN cache pro VEŘEJNÉ read endpointy (free tier, stejná data pro všechny) — Vercel
# edge je servíruje z cache a většina requestů vůbec nesáhne na funkci/DB → škáluje
# do vysoké návštěvnosti. Placené/per-user endpointy (valuation, discovery, smart-money,
# dark-pool, investments, auth, admin) tu NEJSOU — ty se cachovat nesmí (paywall/data).
_CACHEABLE_PREFIXES = ("/api/bias", "/api/gamma", "/api/regime", "/api/dashboard", "/api/news", "/api/summary",
                       "/api/stats", "/api/history", "/api/tickers", "/api/health")
# Přesné cesty (NE prefix): veřejný showcase fondu. /api/fund/signals a /api/fund/ingest jsou
# interní (token) a v CDN cache nesmí nikdy skončit.
_CACHEABLE_EXACT = {"/api/fund"}


@app.middleware("http")
async def _cdn_cache(request, call_next):
    resp = await call_next(request)
    # Přepiš (ne přeskoč) — výchozí 'max-age=0, must-revalidate' by cache zabil.
    path = request.url.path
    if (request.method == "GET" and resp.status_code == 200
            and (path.startswith(_CACHEABLE_PREFIXES) or path in _CACHEABLE_EXACT)):
        resp.headers["Cache-Control"] = "public, s-maxage=60, stale-while-revalidate=600"
    return resp


app.include_router(tickers_router)
app.include_router(news_router)
app.include_router(summary_router)
app.include_router(admin_router)
app.include_router(history_router)
app.include_router(stream_router)
app.include_router(stats_router)
app.include_router(bias_router)
app.include_router(valuation_router)
app.include_router(auth_router)
app.include_router(journal_router)
app.include_router(discovery_router)
app.include_router(gamma_router)
app.include_router(regime_router)
app.include_router(dashboard_router)
app.include_router(smart_money_router)
app.include_router(billing_router)
app.include_router(investments_router)
app.include_router(darkpool_router)
app.include_router(fund_router)


@app.get("/")
async def root():
    return {"app": "Tradezer", "version": "1.2.0",
            "docs": None if _docs_off else "/docs"}

# redeploy trigger 2026-10-05 (fund benchmark + LLM narativ)
