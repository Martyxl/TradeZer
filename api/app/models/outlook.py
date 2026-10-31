"""Modely pre-open výhledu: cache narativu + evaluace scénářů vs realita."""
from datetime import datetime, date

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, Float, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DailyOutlook(Base):
    __tablename__ = "daily_outlook"
    __table_args__ = (UniqueConstraint("ticker_id", "outlook_date", name="uq_daily_outlook"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    outlook_date: Mapped[date] = mapped_column(Date, nullable=False)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class OutlookEval(Base):
    """Vyhodnocení scénáře eventu proti realitě (1 řádek na event × instrument × den).
    Naplňuje denní eval job po zavření eventu; z toho se počítá úspěšnost scénářů."""
    __tablename__ = "outlook_eval"
    __table_args__ = (UniqueConstraint("eval_date", "ticker_id", "event_title", name="uq_outlook_eval"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    eval_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    ticker_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    event_title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    forecast: Mapped[str | None] = mapped_column(String(40))
    actual: Mapped[str | None] = mapped_column(String(40))
    realized_bucket: Mapped[str | None] = mapped_column(String(10))   # hot|inline|cool
    predicted_dir: Mapped[str | None] = mapped_column(String(10))     # up|down|flat
    actual_dir: Mapped[str | None] = mapped_column(String(10))        # up|down|flat
    hit: Mapped[bool | None] = mapped_column(Boolean)
    price_move_pct: Mapped[float | None] = mapped_column(Float)       # ~1h po eventu, %
    event_time_utc: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class OutlookLive(Base):
    """Živá reakce ceny na vydané makro (Twelve Data 1min, worker na Sparku). Body = % pohyb
    od ceny těsně před vydáním po 1/5/15/30/60 min; last = poslední známá cena."""
    __tablename__ = "outlook_live"
    __table_args__ = (UniqueConstraint("event_date", "ticker", "event_title", name="uq_outlook_live"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    event_title: Mapped[str] = mapped_column(String(200), nullable=False)
    event_time_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ticker: Mapped[str] = mapped_column(String(12), nullable=False)
    proxy: Mapped[str | None] = mapped_column(String(12))   # ETF místo futures (SPY/QQQ/DIA)
    p0: Mapped[float] = mapped_column(Float, nullable=False)
    points: Mapped[dict | None] = mapped_column(JSON)        # {"1": pct, "5": pct, ...}
    last_pct: Mapped[float | None] = mapped_column(Float)
    last_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
