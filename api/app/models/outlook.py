"""Cache LLM narativu pro pre-open výhled (1 řádek na instrument a den)."""
from datetime import datetime, date

from sqlalchemy import Date, DateTime, Integer, Text, UniqueConstraint, func
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
