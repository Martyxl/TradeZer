"""MarketDataProvider — rozhraní a typované návratové struktury.

Chybějící hodnota = None (nikdy neimputovat). Všechny dataclasses jsou
JSON-serializovatelné přes asdict → ukládají se do val_raw_snapshots (append-only).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date


@dataclass
class Profile:
    ticker: str
    name: str | None = None
    exchange: str | None = None
    currency: str | None = None
    gics_sector: str | None = None
    gics_industry: str | None = None
    shares_outstanding: float | None = None


@dataclass
class FinancialStatement:
    period_end: str            # ISO date
    period_type: str           # "Q" / "FY"
    report_date: str | None = None
    revenue: float | None = None
    gross_profit: float | None = None
    operating_income: float | None = None
    ebitda: float | None = None
    net_income: float | None = None
    eps_diluted: float | None = None
    shares_diluted: float | None = None
    cfo: float | None = None
    capex: float | None = None
    total_debt: float | None = None
    cash_and_equivalents: float | None = None
    total_equity: float | None = None


@dataclass
class EstimatePoint:
    as_of_date: str
    horizon: str               # current_q / next_q / current_y / next_y
    metric: str                # eps / revenue
    avg: float | None = None
    low: float | None = None
    high: float | None = None
    n_analysts: int | None = None
    year_ago_value: float | None = None


@dataclass
class RevisionTrend:
    as_of_date: str
    horizon: str
    current: float | None = None
    days_ago_7: float | None = None
    days_ago_30: float | None = None
    days_ago_60: float | None = None
    days_ago_90: float | None = None
    up_last_30d: int | None = None
    down_last_30d: int | None = None


@dataclass
class EarningsRow:
    period_end: str
    report_date: str | None = None
    eps_actual: float | None = None
    eps_estimate: float | None = None
    surprise_pct: float | None = None


@dataclass
class PriceBar:
    date: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    adj_close: float | None = None
    volume: float | None = None


@dataclass
class ProviderBundle:
    """Vše k jednomu tickeru z jednoho běhu (usnadňuje cache i ingest)."""
    ticker: str
    profile: Profile | None = None
    financials: list[FinancialStatement] = field(default_factory=list)
    estimates: list[EstimatePoint] = field(default_factory=list)
    revisions: list[RevisionTrend] = field(default_factory=list)
    earnings_history: list[EarningsRow] = field(default_factory=list)
    prices: list[PriceBar] = field(default_factory=list)


class MarketDataProvider(ABC):
    """Jednotné rozhraní zdrojů. Žádné volání ze request pathu — jen z ingest jobu."""

    name: str = "base"

    @abstractmethod
    def get_profile(self, ticker: str) -> Profile | None: ...

    @abstractmethod
    def get_financials(self, ticker: str) -> list[FinancialStatement]: ...

    @abstractmethod
    def get_estimates(self, ticker: str) -> list[EstimatePoint]: ...

    @abstractmethod
    def get_revisions(self, ticker: str) -> list[RevisionTrend]: ...

    @abstractmethod
    def get_earnings_history(self, ticker: str) -> list[EarningsRow]: ...

    @abstractmethod
    def get_prices(self, ticker: str, start: date, end: date) -> list[PriceBar]: ...

    def fetch_bundle(self, ticker: str, price_start: date, price_end: date) -> ProviderBundle:
        """Sesbírá vše k tickeru. Jednotlivé sekce izolované — pád jedné nesmí shodit zbytek."""
        bundle = ProviderBundle(ticker=ticker)
        for attr, fn in (
            ("profile", lambda: self.get_profile(ticker)),
            ("financials", lambda: self.get_financials(ticker)),
            ("estimates", lambda: self.get_estimates(ticker)),
            ("revisions", lambda: self.get_revisions(ticker)),
            ("earnings_history", lambda: self.get_earnings_history(ticker)),
            ("prices", lambda: self.get_prices(ticker, price_start, price_end)),
        ):
            try:
                setattr(bundle, attr, fn())
            except Exception:
                # necháme default (None / prázdný list); ingest zaloguje neúplnost
                pass
        return bundle
