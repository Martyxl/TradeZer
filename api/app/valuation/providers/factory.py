"""Výběr providera podle .env (MARKET_DATA_PROVIDER)."""
from app.config import settings
from app.valuation.providers.base import MarketDataProvider


def get_provider(name: str | None = None) -> MarketDataProvider:
    provider = (name or settings.market_data_provider or "yfinance").lower()
    if provider == "fixture":
        from app.valuation.providers.fixture_provider import FixtureProvider
        return FixtureProvider()
    if provider == "fmp":
        # Volitelný fallback — implementace až bude potřeba (viz sekce 4 specu).
        raise NotImplementedError("FMPProvider zatím není implementován")
    # default
    from app.valuation.providers.yfinance_provider import YFinanceProvider
    return YFinanceProvider()
