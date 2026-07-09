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

        predictions = await self.repo.get_predictions_without_reactions(older_than_minutes=30)
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

                    # Primární okno: 30 min (uloženo do sloupce price_15m / pct_change_15m)
                    price_5m  = _find_close_at(bars, news_utc + timedelta(minutes=5), tolerance_minutes=6)
                    price_10m = _find_close_at(bars, news_utc + timedelta(minutes=10), tolerance_minutes=6)
                    price_30m = _find_close_at(bars, news_utc + timedelta(minutes=30))
                    price_1h  = _find_close_at(bars, news_utc + timedelta(hours=1))
                    price_1d  = _find_close_at(bars, news_utc + timedelta(days=1), tolerance_minutes=60)

                    pct_5m  = _pct(price_5m)
                    pct_10m = _pct(price_10m)
                    pct_30m = _pct(price_30m)
                    pct_1h  = _pct(price_1h)
                    pct_1d  = _pct(price_1d)
                    realized = self._determine_direction(pct_30m, ticker.neutral_threshold)

                    # Liquidity grab detekce: price nejdřív jde opačným směrem,
                    # pak se obrátí na finální směr (klasický stop-hunt před pohybem)
                    def _dir(p: float | None, thr: float) -> int:
                        if p is None or abs(p) < thr * 0.4:
                            return 0
                        return 1 if p > 0 else -1

                    thr = ticker.neutral_threshold
                    dir_5m  = _dir(pct_5m, thr)
                    dir_30m = _dir(pct_30m, thr)
                    # Grab = jasný pohyb v 5min OPAČNÝM směrem než finální 30min pohyb
                    liquidity_grab = (dir_5m != 0 and dir_30m != 0 and dir_5m != dir_30m)

                    price_series = {
                        "pct_5m":  round(pct_5m * 100, 5) if pct_5m is not None else None,
                        "pct_10m": round(pct_10m * 100, 5) if pct_10m is not None else None,
                        "pct_30m": round(pct_30m * 100, 5) if pct_30m is not None else None,
                        "pct_1h":  round(pct_1h * 100, 5) if pct_1h is not None else None,
                        "liquidity_grab": liquidity_grab,
                        "initial_dir": ("up" if dir_5m > 0 else ("down" if dir_5m < 0 else "flat")),
                    }

                    try:
                        await self.repo.save_market_reaction(
                            news_id=pred.news_id,
                            ticker_id=pred.ticker_id,
                            price_at_news=at_news,
                            price_15m=price_30m,   # sloupec price_15m = 30min okno
                            price_1h=price_1h,
                            price_1d=price_1d,
                            pct_change_15m=pct_30m,  # sloupec pct_change_15m = 30min pct
                            pct_change_1h=pct_1h,
                            pct_change_1d=pct_1d,
                            price_series=price_series,
                            realized_direction=realized,
                        )
                        stats["recorded"] += 1
                        log.debug(
                            "Reaction recorded",
                            news_id=pred.news_id,
                            ticker=symbol,
                            pct_30m=pct_30m,
                            realized=realized,
                        )
                    except Exception as e:
                        log.error("save_market_reaction failed", news_id=pred.news_id, error=str(e))
                        stats["failed"] += 1

        await self.session.commit()
        log.info("Calibration job complete", **stats)
        return stats

    async def backfill_price_series(self, days: int = 7) -> dict[str, int]:
        """Doplní price_series (5m/10m/liquidity_grab) do starých MarketReaction záznamů.

        Yahoo Finance 5min data jsou dostupná max. 7 dní zpět, takže backfill
        má smysl jen pro poslední týden.
        """
        log.info("Backfill price_series start", days=days)
        stats = {"checked": 0, "updated": 0, "skipped": 0, "failed": 0}

        reactions = await self.repo.get_reactions_missing_price_series(days=days)
        if not reactions:
            log.info("No reactions to backfill")
            return stats

        # Seskupit podle ticker × datum pro minimální počet HTTP requestů
        groups: dict[tuple, list] = {}
        ticker_threshold: dict[str, float] = {}

        for reaction in reactions:
            stats["checked"] += 1
            if not reaction.news_item or not reaction.ticker:
                stats["skipped"] += 1
                continue
            news_utc = self._to_utc(reaction.news_item.published_at)
            ticker = reaction.ticker
            key = (ticker.symbol, news_utc.date())
            ticker_threshold[ticker.symbol] = ticker.neutral_threshold
            if key not in groups:
                groups[key] = []
            groups[key].append((reaction, news_utc, ticker))

        # Stažení barů — jedna volba Yahoo Finance per ticker × den
        bar_cache: dict[tuple, list] = {}
        for (symbol, for_date) in groups:
            log.info("Backfill fetching bars", symbol=symbol, date=str(for_date))
            try:
                bars = await asyncio.to_thread(self.yahoo.fetch_day_bars, symbol, for_date)
                bar_cache[(symbol, for_date)] = bars
                log.info("Backfill bars OK", symbol=symbol, date=str(for_date), count=len(bars))
            except Exception as e:
                log.warning("Backfill bar fetch failed", symbol=symbol, date=str(for_date), error=str(e))
                bar_cache[(symbol, for_date)] = []

        # Aktualizace price_series
        for (symbol, for_date), items in groups.items():
            bars = bar_cache.get((symbol, for_date), [])
            if not bars:
                stats["skipped"] += len(items)
                continue

            for reaction, news_utc, ticker in items:
                at_news = reaction.price_at_news
                if at_news is None or at_news == 0:
                    stats["skipped"] += 1
                    continue

                def _pct(p: float | None) -> float | None:
                    if p is not None and at_news:
                        return round((p - at_news) / at_news, 6)
                    return None

                try:
                    price_5m  = _find_close_at(bars, news_utc + timedelta(minutes=5), tolerance_minutes=6)
                    price_10m = _find_close_at(bars, news_utc + timedelta(minutes=10), tolerance_minutes=6)

                    pct_5m  = _pct(price_5m)
                    pct_10m = _pct(price_10m)
                    # pct_30m je už uložen v pct_change_15m sloupci (30min okno)
                    pct_30m = reaction.pct_change_15m

                    def _dir(p: float | None, thr: float) -> int:
                        if p is None or abs(p) < thr * 0.4:
                            return 0
                        return 1 if p > 0 else -1

                    thr = ticker.neutral_threshold
                    dir_5m  = _dir(pct_5m, thr)
                    dir_30m = _dir(pct_30m, thr)
                    liquidity_grab = dir_5m != 0 and dir_30m != 0 and dir_5m != dir_30m

                    reaction.price_series = {
                        "pct_5m":  round(pct_5m * 100, 5) if pct_5m is not None else None,
                        "pct_10m": round(pct_10m * 100, 5) if pct_10m is not None else None,
                        "pct_30m": round(pct_30m * 100, 5) if pct_30m is not None else None,
                        "pct_1h":  round(reaction.pct_change_1h * 100, 5) if reaction.pct_change_1h is not None else None,
                        "liquidity_grab": liquidity_grab,
                        "initial_dir": "up" if dir_5m > 0 else ("down" if dir_5m < 0 else "flat"),
                        "backfilled": True,
                    }
                    stats["updated"] += 1
                    log.debug("Backfill updated", reaction_id=reaction.id, ticker=symbol, grab=liquidity_grab)
                except Exception as e:
                    log.error("Backfill reaction failed", reaction_id=reaction.id, error=str(e))
                    stats["failed"] += 1

        await self.session.commit()
        log.info("Backfill price_series complete", **stats)
        return stats
