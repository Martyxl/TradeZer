from app.sources.base import NewsSource, RawNewsItem
from app.sources.forex_factory import ForexFactoryAdapter
from app.sources.rss_adapter import RSSAdapter, build_default_rss_adapters
from app.sources.newsapi_adapter import NewsAPIAdapter
from app.sources.finnhub_adapter import FinnhubAdapter
from app.sources.alphavantage_adapter import AlphaVantageAdapter
from app.sources.yahoo_finance_adapter import YahooFinanceAdapter

__all__ = [
    "NewsSource",
    "RawNewsItem",
    "ForexFactoryAdapter",
    "RSSAdapter",
    "build_default_rss_adapters",
    "NewsAPIAdapter",
    "FinnhubAdapter",
    "AlphaVantageAdapter",
    "YahooFinanceAdapter",
]
