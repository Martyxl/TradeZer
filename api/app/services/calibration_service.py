"""Kalibrační servis — stahuje tržní data a ukládá market reactions."""
import asyncio
from collections import defaultdict
from datetime import timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DirectionEnum
from app.repositories import NewsRepository, TickerRepository
from app.sources.yahoo_finance_adapter import YahooFinanceAdapter, _find_close_at
from datetime import timedelta

log = structlog.get_logger(__name__)


class CalibrationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = NewsRepository(session)
        self.ticker_repo = TickerRepository(session)
        self.yahoo = YahooFinanceAdapter()

    def _determine_direction(self, pct_change: float | None, threshold: float) -> str | None:
        if pct_change is None:
            return None
        if pct_change > threshold:
            return DirectionEnum.UP
        if pct_change < -threshold:
            return DirectionEnum.DOWN
        return DirectionEnum.NEUTRAL

    def _to_utc(self, dt):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    async def run(self) -> dict[str, int]:
        log.info("Calibration job start")
        stats = {"checked": 0, "recorded": 0, "failed": 0, "skipped": 0}

        predictions = await self.repo.get_predictions_without_reactions(older_than_minutes=15)
        if not predictions:
            log.info("No predictions to calibrate")
            return stats

        # Seskupení predikcí: ticker_symbol → date → [predictions]
        groups: dict[str, dict] = defaultdict(lambda: defaultdict(list))
        ticker_map: dict[int, object] = {}

        for pred in predictions:
            stats["checked"] += 1
            ticker = await self.ticker_repo.get_by_id(pred.ticker_id)
            if not ticker:
                stats["skipped"] += 1
                continue
            ticker_map[ticker.id] = ticker
            news_utc = self._to_utc(pred.news_item.published_at)
            groups[ticker.symbol][news_utc.date()].append((pred, news_utc))

        # Stažení cen per ticker × datum (jeden HTTP request = celý den)
        bar_cache: dict[tuple, list] = {}  # (symbol, date) → bars

        for symbol, date_map in groups.items():
            for for_date in date_map:
                cache_key = (symbol, for_date)
                log.info("Fetching price bars", symbol=symbol, date=str(for_date))
                try:
                    bars = await asyncio.to_thread(
                        self.yahoo.fetch_day_bars, symbol, for_date
                    )
                    bar_cache[cache_key] = bars
                    log.info("Bars fetched", symbol=symbol, date=str(for_date), count=len(bars))
                except Exception as e:
                    log.warning("Bar fetch failed", symbol=symbol, date=str(for_date), error=str(e))
                    bar_cache[cache_key] = []

        # Zápis reakcí z cache
        for symbol, date_map in groups.items():
            for for_date, preds in date_map.items():
                bars = bar_cache.get((symbol, for_date), [])
                if not bars:
                    log.warning("No bars for ticker/date", symbol=symbol, date=str(for_date))
                    for pred, _ in preds:
                        stats["skipped"] += 1
                    continue

                for pred, news_utc in preds:
                    ticker = ticker_map[pred.ticker_id]

                    at_news = _find_close_at(bars, news_utc)
                    if at_news is None:
                        log.debug("No price at news time", symbol=symbol, news_time=str(news_utc))
                        stats["skipped"] += 1
                        continue

                    def _pct(p):
                        if p is not None and at_news and at_news != 0:
                            return round((p - at_news) / at_news, 6)
                        return None

                    price_15m = _find_close_at(bars, news_utc + timedelta(minutes=15))
                    price_1h  = _find_close_at(bars, news_utc + timedelta(hours=1))
                    price_1d  = _find_close_at(bars, news_utc + timedelta(days=1), tolerance_minutes=60)

                    pct_15m = _pct(price_15m)
                    pct_1h  = _pct(price_1h)
                    pct_1d  = _pct(price_1d)
                    realized = self._determine_direction(pct_15m, ticker.neutral_threshold)

                    try:
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
                        log.debug(
                            "Reaction recorded",
                            news_id=pred.news_id,
                            ticker=symbol,
                            pct_15m=pct_15m,
                            realized=realized,
                        )
                    except Exception as e:
                        log.error("save_market_reaction failed", news_id=pred.news_id, error=str(e))
                        stats["failed"] += 1

        await self.session.commit()
        log.info("Calibration job complete", **stats)
        return stats
