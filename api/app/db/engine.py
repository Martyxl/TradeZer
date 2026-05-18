from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from app.config import settings


def _build_engine() -> AsyncEngine:
    url = settings.database_url
    if not url.startswith("sqlite") and not url.startswith("postgresql+asyncpg"):
        # Normalize postgres:// → postgresql+asyncpg://
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    if settings.is_sqlite:
        return create_async_engine(url, echo=settings.app_env == "development")
    else:
        return create_async_engine(
            url,
            echo=False,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
        )


engine: AsyncEngine = _build_engine()
