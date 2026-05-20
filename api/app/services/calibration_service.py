"""Kalibrační servis — stahuje tržní data a ukládá market reactions."""
import asyncio
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DirectionEnum
from app.repositories import NewsRepository, TickerRepository
from app.sources.yahoo_finance_adapter import YahooFinanceAdapter

log = structlog.get_logger(__name__)


class CalibrationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = NewsRepository(session)
        self.ticker_repo = TickerRepository(session)
        self.yahoo = YahooFinanceAdapter()

    def _determine_direction(
        self, pct_change: float | None, threshold: float
    ) -> str | None:
        if pct_change is None:
            return None
        if pct_change > threshold:
            return DirectionEnum.UP
        if pct_change < -threshold:
            return DirectionEnum.DOWN
        return DirectionEnum.NEUTRAL

    async def run(self) -> dict[str, int]:
        log.info("Calibration job start")
        stats = {"checked": 0, "recorded": 0, "failed": 0, "skipped": 0}

        predictions = await self.repo.get_predictions_without_reactions(older_than_minutes=1)

        for pred in predictions:
            stats["checked"] += 1
            ticker = await self.ticker_repo.get_by_id(pred.ticker_id)
            if not ticker:
                stats["skipped"] += 1
                continue

            news_time = pred.news_item.published_at
            try:
                # yfinance je synchronní — spustíme v thread poolu aby neblokoval
                prices = await asyncio.to_thread(
                    self.yahoo.get_prices_for_reaction, ticker.symbol, news_time
                )
            except Exception as e:
                log.warning("Yahoo Finance failed", news_id=pred.news_id, ticker=ticker.symbol, error=str(e))
                stats["failed"] += 1
                continue

            at_news = prices.get("at_news")
            price_15m = prices.get("15m")
            price_1h = prices.get("1h")
            price_1d = prices.get("1d")

            # Bez ceny v čase zprávy nemůžeme spočítat % změnu
            if at_news is None:
                log.debug("No price at news time", news_id=pred.news_id, ticker=ticker.symbol)
                stats["skipped"] += 1
                continue

            def _pct(p: float | None) -> float | None:
                if p and at_news and at_news != 0:
                    return round((p - at_news) / at_news, 6)
                return None

            pct_15m = _pct(price_15m)
            pct_1h = _pct(price_1h)
            pct_1d = _pct(price_1d)

            # Realizovaný směr = pohyb za 15 minut (nejrychlejší reakce trhu)
            realized = self._determine_direction(pct_15m, ticker.neutral_threshold)

            await self.repo.save_market_reaction(
                news_id=pred.news_id,
                ticker_id=pred.ticker_id,
                price_at_news=at_news,
                price_15m=price_15m,
                price_1h=price_1h,
                price_1d=price_1d,
                pct_change_15m=pct_15m,
                pct_change_1h=pct_1h,
                pct_change_1d=pct_1d,
                realized_direction=realized,
            )
            stats["recorded"] += 1
            log.info(
                "Reaction recorded",
                news_id=pred.news_id,
                ticker=ticker.symbol,
                pct_15m=pct_15m,
                realized=realized,
            )

        await self.session.commit()
        log.info("Calibration job complete", **stats)
        return stats
