from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.news import NewsTicker, NewsPrediction, MarketReaction, DailySummary


class Ticker(Base):
    __tablename__ = "tickers"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(50), nullable=False, default="forex")
    source_symbol_map: Mapped[dict] = mapped_column(JSON, default=dict)
    neutral_threshold: Mapped[float] = mapped_column(default=0.002)
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    relevances: Mapped[list["NewsTicker"]] = relationship(back_populates="ticker")
    predictions: Mapped[list["NewsPrediction"]] = relationship(back_populates="ticker")
    market_reactions: Mapped[list["MarketReaction"]] = relationship(back_populates="ticker")
    daily_summaries: Mapped[list["DailySummary"]] = relationship(back_populates="ticker")
