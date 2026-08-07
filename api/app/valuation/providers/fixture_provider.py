"""FixtureProvider — čte zmrazené JSON z disku. Používá se ve VŠECH testech.

Testy nikdy nesmí síťovat. Fixture = tests/fixtures/valuation/<TICKER>.json
se strukturou: {profile, financials, estimates, revisions, earnings_history, prices}.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.valuation.providers.base import (
    MarketDataProvider, Profile, FinancialStatement, EstimatePoint,
    RevisionTrend, EarningsRow, PriceBar,
)

DEFAULT_FIXTURE_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "valuation"


class FixtureProvider(MarketDataProvider):
    name = "fixture"

    def __init__(self, fixture_dir: Path | str | None = None):
        self.dir = Path(fixture_dir) if fixture_dir else DEFAULT_FIXTURE_DIR

    def _load(self, ticker: str) -> dict:
        path = self.dir / f"{ticker}.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def get_profile(self, ticker: str) -> Profile | None:
        p = self._load(ticker).get("profile")
        return Profile(ticker=ticker, **p) if p else None

    def get_financials(self, ticker: str) -> list[FinancialStatement]:
        return [FinancialStatement(**r) for r in self._load(ticker).get("financials", [])]

    def get_estimates(self, ticker: str) -> list[EstimatePoint]:
        return [EstimatePoint(**r) for r in self._load(ticker).get("estimates", [])]

    def get_revisions(self, ticker: str) -> list[RevisionTrend]:
        return [RevisionTrend(**r) for r in self._load(ticker).get("revisions", [])]

    def get_earnings_history(self, ticker: str) -> list[EarningsRow]:
        return [EarningsRow(**r) for r in self._load(ticker).get("earnings_history", [])]

    def get_prices(self, ticker: str, start: date, end: date) -> list[PriceBar]:
        bars = [PriceBar(**r) for r in self._load(ticker).get("prices", [])]
        s, e = start.isoformat(), end.isoformat()
        return [b for b in bars if b.date and s <= b.date <= e]
