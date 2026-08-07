"""Datové zdroje pro Valuation Radar (adapter pattern).

MarketDataProvider = jednotné rozhraní. Výměna zdroje = jedna třída,
aby přechod z yfinance na licencovaný feed byl triviální (viz sekce 4 specu).
"""
from app.valuation.providers.base import (
    MarketDataProvider,
    Profile,
    FinancialStatement,
    EstimatePoint,
    RevisionTrend,
    EarningsRow,
    PriceBar,
)
from app.valuation.providers.factory import get_provider

__all__ = [
    "MarketDataProvider",
    "Profile",
    "FinancialStatement",
    "EstimatePoint",
    "RevisionTrend",
    "EarningsRow",
    "PriceBar",
    "get_provider",
]
