from datetime import datetime, date
from typing import TYPE_CHECKING

from sqlalchemy import (
    String, Text, DateTime, Date, Float, Boolean, Integer,
    ForeignKey, UniqueConstraint, JSON, Enum
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import enum

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.ticker import Ticker


class DirectionEnum(str, enum.Enum):
    DOWN = "down"
    NEUTRAL = "neutral"
    UP = "up"


class NewsSource(Base):
    __tablename__ = "news_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    source_weight: Mapped[float] = mapped_column(Float, default=0.5)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    news_items: Mapped[list["NewsItem"]] = relationship(back_populates="source")


class NewsItem(Base):
    __tablename__ = "news_items"
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_source_external"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("news_sources.id"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)

    source: Mapped["NewsSource"] = relationship(back_populates="news_items")
    ticker_relevances: Mapped[list["NewsTicker"]] = relationship(back_populates="news_item")
    predictions: Mapped[list["NewsPrediction"]] = relationship(back_populates="news_item")
    market_reactions: Mapped[list["MarketReaction"]] = relationship(back_populates="news_item")
    categories: Mapped[list["NewsItemCategory"]] = relationship(back_populates="news_item")


class NewsTicker(Base):
    __tablename__ = "news_ticker_relevance"
    __table_args__ = (UniqueConstraint("news_id", "ticker_id", name="uq_news_ticker"),)

    news_id: Mapped[int] = mapped_column(ForeignKey("news_items.id"), primary_key=True)
    ticker_id: Mapped[int] = mapped_column(ForeignKey("tickers.id"), primary_key=True)
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    importance_weight: Mapped[float] = mapped_column(Float, default=0.0)
    llm_rationale: Mapped[str | None] = mapped_column(Text)

    news_item: Mapped["NewsItem"] = relationship(back_populates="ticker_relevances")
    ticker: Mapped["Ticker"] = relationship(back_populates="relevances")


class NewsPrediction(Base):
    __tablename__ = "news_predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    news_id: Mapped[int] = mapped_column(ForeignKey("news_items.id"), nullable=False, index=True)
    ticker_id: Mapped[int] = mapped_column(ForeignKey("tickers.id"), nullable=False)
    prob_down: Mapped[float] = mapped_column(Float, nullable=False)
    prob_neutral: Mapped[float] = mapped_column(Float, nullable=False)
    prob_up: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    model_version: Mapped[str] = mapped_column(String(50), default="claude-sonnet-4-6")
    llm_reasoning: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    news_item: Mapped["NewsItem"] = relationship(back_populates="predictions")
    ticker: Mapped["Ticker"] = relationship(back_populates="predictions")


class MarketReaction(Base):
    __tablename__ = "market_reactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    news_id: Mapped[int] = mapped_column(ForeignKey("news_items.id"), nullable=False, index=True)
    ticker_id: Mapped[int] = mapped_column(ForeignKey("tickers.id"), nullable=False)
    price_at_news: Mapped[float | None] = mapped_column(Float)
    price_15m: Mapped[float | None] = mapped_column(Float)   # uloženo 30min okno
    price_1h: Mapped[float | None] = mapped_column(Float)
    price_1d: Mapped[float | None] = mapped_column(Float)
    pct_change_15m: Mapped[float | None] = mapped_column(Float)  # = 30min pct
    pct_change_1h: Mapped[float | None] = mapped_column(Float)
    pct_change_1d: Mapped[float | None] = mapped_column(Float)
    # price_series: vývoj ceny v klíčových okamžicích (5m, 10m, 30m, 60m) + liquidity_grab detekce
    price_series: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    realized_direction: Mapped[str | None] = mapped_column(
        Enum(DirectionEnum), nullable=True
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    news_item: Mapped["NewsItem"] = relationship(back_populates="market_reactions")
    ticker: Mapped["Ticker"] = relationship(back_populates="market_reactions")


class NewsCategory(Base):
    __tablename__ = "news_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    news_items: Mapped[list["NewsItemCategory"]] = relationship(back_populates="category")


class NewsItemCategory(Base):
    __tablename__ = "news_item_categories"

    news_id: Mapped[int] = mapped_column(ForeignKey("news_items.id"), primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("news_categories.id"), primary_key=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    news_item: Mapped["NewsItem"] = relationship(back_populates="categories")
    category: Mapped["NewsCategory"] = relationship(back_populates="news_items")


class DailySummary(Base):
    __tablename__ = "daily_summaries"
    __table_args__ = (UniqueConstraint("ticker_id", "date", name="uq_ticker_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker_id: Mapped[int] = mapped_column(ForeignKey("tickers.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    overall_prob_down: Mapped[float] = mapped_column(Float, default=0.333)
    overall_prob_neutral: Mapped[float] = mapped_column(Float, default=0.334)
    overall_prob_up: Mapped[float] = mapped_column(Float, default=0.333)
    recommendation: Mapped[str | None] = mapped_column(Text)
    top_drivers: Mapped[dict] = mapped_column(JSON, default=list)
    generated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    ticker: Mapped["Ticker"] = relationship(back_populates="daily_summaries")
