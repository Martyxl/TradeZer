from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
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

    if settings.is_sqlite:
        return create_async_engine(url, echo=settings.app_env == "development")
    else:
        return create_async_engine(
            url,
            echo=False,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            connect_args=connect_args,
        )


engine: AsyncEngine = _build_engine()
