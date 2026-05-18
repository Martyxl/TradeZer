"""Denní summary servis — agreguje zprávy a generuje doporučení."""
from datetime import date

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import llm_client
from app.models import NewsItem, NewsTicker, NewsPrediction
from app.repositories import NewsRepository, TickerRepository

log = structlog.get_logger(__name__)


class SummaryService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = NewsRepository(session)
        self.ticker_repo = TickerRepository(session)

    async def generate_for_ticker(self, ticker_id: int, for_date: date) -> None:
        ticker = await self.ticker_repo.get_by_id(ticker_id)
        if not ticker:
            return

        # Načteme zprávy a predikce za daný den
        stmt = (
            select(
                NewsPrediction.prob_down,
                NewsPrediction.prob_neutral,
                NewsPrediction.prob_up,
                NewsTicker.importance_weight,
                NewsItem.id.label("news_id"),
                NewsItem.title,
            )
            .join(NewsItem, NewsItem.id == NewsPrediction.news_id)
            .join(NewsTicker, (NewsTicker.news_id == NewsPrediction.news_id) & (NewsTicker.ticker_id == ticker_id))
            .where(
                NewsPrediction.ticker_id == ticker_id,
                func.date(NewsItem.published_at) == for_date,
            )
            .order_by(NewsTicker.importance_weight.desc())
        )
        result = await self.session.execute(stmt)
        rows = result.all()

        if not rows:
            log.info("No news for summary", ticker=ticker.symbol, date=str(for_date))
            return

        total_weight = sum(r.importance_weight for r in rows) or 1.0
        overall_down = sum(r.prob_down * r.importance_weight for r in rows) / total_weight
        overall_neutral = sum(r.prob_neutral * r.importance_weight for r in rows) / total_weight
        overall_up = sum(r.prob_up * r.importance_weight for r in rows) / total_weight

        # Normalize
        total = overall_down + overall_neutral + overall_up or 1.0
        overall_down /= total
        overall_neutral /= total
        overall_up /= total

        top_news = [
            {
                "news_id": r.news_id,
                "title": r.title,
                "weight": r.importance_weight,
                "direction": (
                    "UP" if r.prob_up > r.prob_down and r.prob_up > r.prob_neutral
                    else "DOWN" if r.prob_down > r.prob_neutral
                    else "NEUTRAL"
                ),
            }
            for r in rows[:5]
        ]

        recommendation = llm_client.generate_daily_recommendation(
            ticker=ticker.symbol,
            prob_down=overall_down,
            prob_neutral=overall_neutral,
            prob_up=overall_up,
            top_news=top_news,
            date_str=str(for_date),
        )

        await self.repo.upsert_daily_summary(
            ticker_id=ticker_id,
            for_date=for_date,
            prob_down=overall_down,
            prob_neutral=overall_neutral,
            prob_up=overall_up,
            recommendation=recommendation,
            top_drivers={"news": top_news},
        )
        await self.session.commit()
        log.info("Daily summary generated", ticker=ticker.symbol, date=str(for_date))

    async def generate_all(self, for_date: date) -> None:
        tickers = await self.ticker_repo.get_all_enabled()
        for ticker in tickers:
            try:
                await self.generate_for_ticker(ticker.id, for_date)
            except Exception as e:
                log.error("Summary failed", ticker=ticker.symbol, error=str(e))
