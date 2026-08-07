"""Pydantic schémata pro Valuation API. Žádné volné dicty ven z API."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel

DISCLAIMER = (
    "Heuristická analýza z veřejných dat s nejistou kvalitou — NENÍ investiční "
    "doporučení. Konsenzus analytiků bývá systematicky optimistický; modul slouží "
    "jako filtr a rozcestník k dalšímu zkoumání, ne jako rozhodovací mechanismus."
)


class Meta(BaseModel):
    as_of_date: date | None = None
    model_version: str
    data_source: str
    disclaimer: str = DISCLAIMER


class GroupOut(BaseModel):
    key: str
    label_cs: str
    label_en: str
    color_hex: str
    sort_order: int


class GroupsResponse(BaseModel):
    meta: Meta
    groups: list[GroupOut]


class OverviewItem(BaseModel):
    ticker: str
    name: str | None = None
    group_key: str | None = None
    # osy bublinové mapy
    pctile_pe_fwd: float | None = None       # X
    eps_growth_ntm: float | None = None      # Y
    market_cap: float | None = None          # velikost
    # skóre + verdikty
    valuation_score: float | None = None
    composite_score: float | None = None
    valuation_verdict: str | None = None
    horizon_verdict: str | None = None
    bubble_flag: bool = False
    confidence: float | None = None


class OverviewResponse(BaseModel):
    meta: Meta
    items: list[OverviewItem]


class DriverItem(BaseModel):
    name: str
    value: float | None = None
    contribution: float | None = None


class FinancialRow(BaseModel):
    period_end: date
    period_type: str
    revenue: float | None = None
    net_income: float | None = None
    eps_diluted: float | None = None
    operating_income: float | None = None


class EstimateRow(BaseModel):
    horizon: str
    metric: str
    avg: float | None = None
    low: float | None = None
    high: float | None = None
    n_analysts: int | None = None
    year_ago_value: float | None = None


class EarningsRow(BaseModel):
    period_end: date
    eps_actual: float | None = None
    eps_estimate: float | None = None
    surprise_pct: float | None = None


class ValuationDetail(BaseModel):
    meta: Meta
    ticker: str
    name: str | None = None
    group_key: str | None = None
    # skóre
    valuation_score: float | None = None
    growth_score: float | None = None
    quality_score: float | None = None
    revision_score: float | None = None
    trend_score: float | None = None
    composite_score: float | None = None
    valuation_verdict: str | None = None
    horizon_verdict: str | None = None
    bubble_flag: bool = False
    confidence: float | None = None
    unreliable: bool = False
    drivers: dict[str, list[DriverItem]] = {}
    metrics: dict = {}
    latest_financials: list[FinancialRow] = []
    estimates: list[EstimateRow] = []
    earnings_history: list[EarningsRow] = []


class HistoryPoint(BaseModel):
    as_of_date: date
    valuation_score: float | None = None
    composite_score: float | None = None
    confidence: float | None = None
    bubble_flag: bool = False


class HistoryResponse(BaseModel):
    meta: Meta
    ticker: str
    points: list[HistoryPoint]


class RefreshResponse(BaseModel):
    meta: Meta
    status: str
    run_id: int | None = None
    stages: dict[str, dict] = {}


class RunOut(BaseModel):
    meta: Meta
    run_id: int
    started_at: str | None = None
    finished_at: str | None = None
    tickers_ok: int
    tickers_failed: int
    notes: str | None = None
