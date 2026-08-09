"""Výběr providera podle .env (MARKET_DATA_PROVIDER)."""
from app.config import settings
from app.valuation.providers.base import MarketDataProvider


def get_provider(name: str | None = None) -> MarketDataProvider:
    provider = (name or settings.market_data_provider or "yfinance").lower()
    # yfinance je z cloud/CI IP nefunkční (Yahoo blokuje) → když je FMP klíč,
    # automaticky preferuj FMP i bez explicitního MARKET_DATA_PROVIDER=fmp.
    if provider == "yfinance" and settings.fmp_api_key:
        provider = "fmp"
    if provider == "sec":
        from app.valuation.providers.sec_provider import SECEdgarProvider
        return SECEdgarProvider()
    if provider == "fixture":
        from app.valuation.providers.fixture_provider import FixtureProvider
        return FixtureProvider()
    if provider == "fmp":
        from app.valuation.providers.fmp_provider import FMPProvider
        return FMPProvider()
    # default
    from app.valuation.providers.yfinance_provider import YFinanceProvider
    return YFinanceProvider()
