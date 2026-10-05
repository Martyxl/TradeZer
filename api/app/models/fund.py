"""TRADEZER investuje — AI paper-trading fond (display kopie v Neonu).

Autoritativní stav drží Spark (lokální SQLite, řídí algoritmus). Spark pushuje
zrcadlo sem přes POST /api/fund/ingest; frontend čte přes GET /api/fund.
Start kapitál 1 000 000 CZK. Každý obchod má důvod (reason).
"""
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FundState(Base):
    """Singleton (id=1) — hotovost, start kapitál, celková hodnota, poslední běh."""
    __tablename__ = "fund_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    start_capital: Mapped[float] = mapped_column(Float, default=1_000_000.0, nullable=False)
    cash: Mapped[float] = mapped_column(Float, default=1_000_000.0, nullable=False)
    equity: Mapped[float] = mapped_column(Float, default=1_000_000.0, nullable=False)  # cash + pozice
    base: Mapped[str] = mapped_column(String(8), default="CZK", nullable=False)
    as_of: Mapped[datetime | None] = mapped_column(DateTime)
    note: Mapped[str | None] = mapped_column(Text)  # krátký souhrn poslední strategie/rozhodnutí


class FundPosition(Base):
    """Aktuální otevřená pozice fondu (replace při každém pushi)."""
    __tablename__ = "fund_positions"

    symbol: Mapped[str] = mapped_column(String(24), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(120))
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    avg_cost: Mapped[float] = mapped_column(Float, nullable=False)        # v měně titulu
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    last_price: Mapped[float | None] = mapped_column(Float)
    value_czk: Mapped[float | None] = mapped_column(Float)
    unrealized_czk: Mapped[float | None] = mapped_column(Float)
    weight_pct: Mapped[float | None] = mapped_column(Float)
    opened_at: Mapped[str | None] = mapped_column(String(10))             # datum prvního nákupu
    conviction: Mapped[float | None] = mapped_column(Float)               # aktuální skóre konvikce


class FundTrade(Base):
    """Záznam obchodu (append-only log, replace celého logu při pushi)."""
    __tablename__ = "fund_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[str] = mapped_column(String(19), index=True)               # ISO datetime
    action: Mapped[str] = mapped_column(String(8), nullable=False)        # buy | sell | trim
    symbol: Mapped[str] = mapped_column(String(24), nullable=False)
    name: Mapped[str | None] = mapped_column(String(120))
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    value_czk: Mapped[float | None] = mapped_column(Float)
    realized_czk: Mapped[float | None] = mapped_column(Float)             # u prodeje realizovaný P/L
    conviction: Mapped[float | None] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text, nullable=False)             # PROČ se obchod stal


class FundSnapshot(Base):
    """Denní bod equity křivky (upsert dle data)."""
    __tablename__ = "fund_snapshots"

    date: Mapped[str] = mapped_column(String(10), primary_key=True)       # YYYY-MM-DD
    equity: Mapped[float] = mapped_column(Float, nullable=False)          # celková hodnota CZK
    cash: Mapped[float] = mapped_column(Float, nullable=False)
    invested: Mapped[float] = mapped_column(Float, nullable=False)        # hodnota pozic CZK
    benchmark: Mapped[float | None] = mapped_column(Float)                # 1 mil. v S&P 500 (index return)
