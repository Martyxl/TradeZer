from app.routers.tickers import router as tickers_router
from app.routers.news import router as news_router
from app.routers.summary import router as summary_router
from app.routers.admin import router as admin_router
from app.routers.history import router as history_router
from app.routers.stream import router as stream_router

__all__ = [
    "tickers_router",
    "news_router",
    "summary_router",
    "admin_router",
    "history_router",
    "stream_router",
]
