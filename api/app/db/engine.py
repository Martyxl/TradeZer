from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy.pool import NullPool

from app.config import settings


def _build_engine() -> AsyncEngine:
    url = settings.database_url
    connect_args: dict = {}

    if not url.startswith("sqlite"):
        # Normalize postgres:// → postgresql+asyncpg://
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

        # asyncpg nepodporuje sslmode= v URL — odstraníme ho a předáme ssl přes connect_args
        if "sslmode=" in url:
            url = url.split("?")[0]
            connect_args["ssl"] = True
        # Vercel serverless + Neon pooler (PgBouncer): bez perzistentního poolu.
        # NullPool = každá krátká funkce si vezme a vrátí spojení do PgBounceru,
        # žádné hromadění idle spojení přes mnoho instancí → neteče do limitu Neonu.
        # statement_cache_size=0 je nutné pro PgBouncer transaction mode (jinak
        # kolidují pojmenované prepared statements asyncpg).
        connect_args["statement_cache_size"] = 0

    if settings.is_sqlite:
        return create_async_engine(url, echo=settings.app_env == "development")
    return create_async_engine(
        url,
        echo=False,
        poolclass=NullPool,
        connect_args=connect_args,
    )


engine: AsyncEngine = _build_engine()
