"""Valuation Radar — datový model (PostgreSQL, append-only snapshoty).

Konvence repa: tabulky vznikají přes Base.metadata.create_all (viz main.py),
JSONB jen na Postgresu (na SQLite ve vývoji/testech spadne na JSON).
"""
from datetime import date, datetime

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String,
    UniqueConstraint, Index, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# JSONB na Postgresu, JSON na SQLite (testy/vývoj)
JSONType = JSON().with_variant(JSONB(), "postgresql")


class ValGroup(Base):
    __tablename__ = "val_groups"

    key: Mapped[str] = mapped_column(String(30), primary_key=True)
    label_cs: Mapped[str] = mapped_column(String(80), nullable=False)
    label_en: Mapped[str] = mapped_column(String(80), nullable=False)
    color_hex: Mapped[str] = mapped_column(String(9), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str | None] = mapped_column(String(300))


class ValInstrument(Base):
    __tablename__ = "val_instruments"

    ticker: Mapped[str] = mapped_column(String(12), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(120))
    exchange: Mapped[str | None] = mapped_column(String(20))
    currency: Mapped[str | None] = mapped_column(String(8))
    gics_sector: Mapped[str | None] = mapped_column(String(60))
    gics_industry: Mapped[str | None] = mapped_column(String(80))
    group_key: Mapped[str | None] = mapped_column(ForeignKey("val_groups.key"), index=True)
    in_display_universe: Mapped[bool] = mapped_column(Boolean, default=False)
    in_peer_universe: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ValRawSnapshot(Base):
    """Append-only surové odpovědi providerů. NIKDY UPDATE/DELETE."""
    __tablename__ = "val_raw_snapshots"
    __table_args__ = (
        UniqueConstraint("ticker", "source", "endpoint", "as_of_date", name="uq_val_raw"),
        Index("ix_val_raw_ticker_date", "ticker", "as_of_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(12), nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(40), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONType, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ValFinancials(Base):
    """Výkazy. Revize = nový řádek (revision_no), ne UPDATE."""
    __tablename__ = "val_financials"
    __table_args__ = (
        UniqueConstraint("ticker", "period_end", "period_type", "revision_no", name="uq_val_fin"),
        Index("ix_val_fin_ticker_date", "ticker", "period_end"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(12), nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    period_type: Mapped[str] = mapped_column(String(2), nullable=False)  # Q / FY
    report_date: Mapped[date | None] = mapped_column(Date)               # kdy vydáno (anti look-ahead)
    revenue: Mapped[float | None] = mapped_column(Float)
    gross_profit: Mapped[float | None] = mapped_column(Float)
    operating_income: Mapped[float | None] = mapped_column(Float)
    ebitda: Mapped[float | None] = mapped_column(Float)
    net_income: Mapped[float | None] = mapped_column(Float)
    eps_diluted: Mapped[float | None] = mapped_column(Float)
    shares_diluted: Mapped[float | None] = mapped_column(Float)
    cfo: Mapped[float | None] = mapped_column(Float)
    capex: Mapped[float | None] = mapped_column(Float)
    total_debt: Mapped[float | None] = mapped_column(Float)
    cash_and_equivalents: Mapped[float | None] = mapped_column(Float)
    total_equity: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    revision_no: Mapped[int] = mapped_column(Integer, default=0)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ValEstimate(Base):
    __tablename__ = "val_estimates"
    __table_args__ = (
        UniqueConstraint("ticker", "as_of_date", "horizon", "metric", name="uq_val_est"),
        Index("ix_val_est_ticker_date", "ticker", "as_of_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(12), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    horizon: Mapped[str] = mapped_column(String(12), nullable=False)  # current_q/next_q/current_y/next_y
    metric: Mapped[str] = mapped_column(String(10), nullable=False)   # eps/revenue
    avg: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    n_analysts: Mapped[int | None] = mapped_column(Integer)
    year_ago_value: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(30), nullable=False)


class ValEstimateTrend(Base):
    __tablename__ = "val_estimate_trend"
    __table_args__ = (
        UniqueConstraint("ticker", "as_of_date", "horizon", name="uq_val_esttrend"),
        Index("ix_val_esttrend_ticker_date", "ticker", "as_of_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(12), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    horizon: Mapped[str] = mapped_column(String(12), nullable=False)
    current: Mapped[float | None] = mapped_column(Float)
    days_ago_7: Mapped[float | None] = mapped_column(Float)
    days_ago_30: Mapped[float | None] = mapped_column(Float)
    days_ago_60: Mapped[float | None] = mapped_column(Float)
    days_ago_90: Mapped[float | None] = mapped_column(Float)
    up_last_30d: Mapped[int | None] = mapped_column(Integer)
    down_last_30d: Mapped[int | None] = mapped_column(Integer)


class ValEarningsHistory(Base):
    __tablename__ = "val_earnings_history"
    __table_args__ = (
        UniqueConstraint("ticker", "period_end", name="uq_val_earn"),
        Index("ix_val_earn_ticker_date", "ticker", "period_end"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(12), nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    report_date: Mapped[date | None] = mapped_column(Date)
    eps_actual: Mapped[float | None] = mapped_column(Float)
    eps_estimate: Mapped[float | None] = mapped_column(Float)
    surprise_pct: Mapped[float | None] = mapped_column(Float)


class ValPriceDaily(Base):
    __tablename__ = "val_prices_daily"
    __table_args__ = (
        UniqueConstraint("ticker", "date", name="uq_val_price"),
        Index("ix_val_price_ticker_date", "ticker", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(12), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    close: Mapped[float | None] = mapped_column(Float)
    adj_close: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float)


class ValMetricsDaily(Base):
    """Spočítané metriky (sekce 6 specu). Doplní se sloupci ve fázi P2."""
    __tablename__ = "val_metrics_daily"
    __table_args__ = (
        UniqueConstraint("ticker", "as_of_date", "model_version", name="uq_val_metrics"),
        Index("ix_val_metrics_ticker_date", "ticker", "as_of_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(12), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Kompletní sada metrik jako JSON — konkrétní sloupce se přidají v P2 dle potřeby,
    # tady držíme audit-friendly bag, ať P0 schéma nemusí předjímat všech ~40 metrik.
    metrics: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    model_version: Mapped[str] = mapped_column(String(20), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ValScoreDaily(Base):
    __tablename__ = "val_scores_daily"
    __table_args__ = (
        UniqueConstraint("ticker", "as_of_date", "model_version", name="uq_val_scores"),
        Index("ix_val_scores_ticker_date", "ticker", "as_of_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(12), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    valuation_score: Mapped[float | None] = mapped_column(Float)
    growth_score: Mapped[float | None] = mapped_column(Float)
    quality_score: Mapped[float | None] = mapped_column(Float)
    revision_score: Mapped[float | None] = mapped_column(Float)
    trend_score: Mapped[float | None] = mapped_column(Float)
    composite_score: Mapped[float | None] = mapped_column(Float)
    valuation_verdict: Mapped[str | None] = mapped_column(String(20))
    horizon_verdict: Mapped[str | None] = mapped_column(String(20))
    bubble_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    drivers: Mapped[dict | None] = mapped_column(JSONType)  # top 3 +/- faktory
    model_version: Mapped[str] = mapped_column(String(20), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ValSummary(Base):
    """Cache LLM shrnutí. Klíč = hash vstupních čísel → stejná čísla se negenerují znovu."""
    __tablename__ = "val_summaries"
    __table_args__ = (
        UniqueConstraint("ticker", "input_hash", name="uq_val_summary"),
        Index("ix_val_summary_ticker", "ticker"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(12), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str] = mapped_column(String(2000), nullable=False)
    llm_model: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ValScoreRun(Base):
    __tablename__ = "val_score_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    model_version: Mapped[str] = mapped_column(String(20), nullable=False)
    tickers_ok: Mapped[int] = mapped_column(Integer, default=0)
    tickers_failed: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(String(500))
