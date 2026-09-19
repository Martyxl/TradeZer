from app.routers.tickers import router as tickers_router
from app.routers.news import router as news_router
from app.routers.summary import router as summary_router
from app.routers.admin import router as admin_router
from app.routers.history import router as history_router
from app.routers.stream import router as stream_router
from app.routers.stats import router as stats_router
from app.routers.bias import router as bias_router
from app.routers.valuation import router as valuation_router
from app.routers.auth import router as auth_router
from app.routers.journal import router as journal_router
from app.routers.discovery import router as discovery_router
from app.routers.gamma import router as gamma_router
from app.routers.smart_money import router as smart_money_router

__all__ = [
    "bias_router",
    "valuation_router",
    "auth_router",
    "journal_router",
    "discovery_router",
    "gamma_router",
    "smart_money_router",
    "tickers_router",
    "news_router",
    "summary_router",
    "admin_router",
    "history_router",
    "stream_router",
    "stats_router",
]
