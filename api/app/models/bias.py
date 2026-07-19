"""Denní BIAS — snapshot očekávaného směru dne + vyhodnocení reality."""
from datetime import datetime, date

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DailyBias(Base):
    __tablename__ = "daily_bias"
    __table_args__ = (UniqueConstraint("ticker_id", "bias_date", name="uq_bias_ticker_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker_id: Mapped[int] = mapped_column(ForeignKey("tickers.id"), nullable=False, index=True)
    bias_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    prob_down: Mapped[float] = mapped_column(Float, nullable=False)
    prob_neutral: Mapped[float] = mapped_column(Float, nullable=False)
    prob_up: Mapped[float] = mapped_column(Float, nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # up/down/neutral
    trust_score: Mapped[float] = mapped_column(Float, default=0.0)      # 0-100
    n_news: Mapped[int] = mapped_column(Integer, default=0)
    avg_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Vyhodnocení: pohyb London open (07:00 UTC) -> NY close (21:00 UTC)
    realized_direction: Mapped[str | None] = mapped_column(String(10), nullable=True)
    realized_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
