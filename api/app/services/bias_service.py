"""Denní BIAS: agregace ranních predikcí -> směr dne, snapshot v London open,
vyhodnocení proti realitě (pohyb 07:00 -> 21:00 UTC) a statistika úspěšnosti.

Obchodní den = 22:00 UTC předchozího dne až 22:00 UTC. Snapshot se dělá při
prvním zpracování po 07:00 UTC (London open) z predikcí zpráv publikovaných
od začátku obchodního dne.
"""
import asyncio
import math
from datetime import datetime, date, time, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DailyBias, NewsItem, NewsPrediction, Ticker
from app.sources.yahoo_finance_adapter import YahooFinanceAdapter, _find_close_at

log = structlog.get_logger(__name__)

LONDON_OPEN_UTC = time(7, 0)
NY_CLOSE_UTC = time(21, 0)
DAY_START_SHIFT_H = 2  # 22:00 UTC = začátek obchodního dne


def _trading_day(now: datetime) -> date:
    return (now + timedelta(hours=DAY_START_SHIFT_H)).date()


def _day_start_utc(tday: date) -> datetime:
    return datetime.combine(tday - timedelta(days=1), time(22, 0), tzinfo=None)


async def compute_bias(session: AsyncSession, ticker: Ticker, tday: date,
                       until: datetime | None = None) -> dict:
    """Váženě zprůměruje predikce zpráv obchodního dne (volitelně do času `until`)."""
    start = _day_start_utc(tday)
    stmt = (
        select(NewsPrediction, NewsItem.published_at)
        .join(NewsItem, NewsItem.id == NewsPrediction.news_id)
        .where(NewsPrediction.ticker_id == ticker.id)
        .where(NewsItem.published_at >= start)
        .where(NewsPrediction.confidence > 0.0)
    )
    if until is not None:
        stmt = stmt.where(NewsItem.published_at <= until)
    rows = (await session.execute(stmt)).all()

    if not rows:
        return {"n_news": 0, "prob_down": 0.333, "prob_neutral": 0.334, "prob_up": 0.333,
                "direction": "neutral", "trust_score": 0.0, "avg_confidence": 0.0}

    tw = td = tn = tu = tc = 0.0
    for pred, _pub in rows:
        w = max(pred.confidence, 0.05)
        tw += w
        td += w * pred.prob_down
        tn += w * pred.prob_neutral
        tu += w * pred.prob_up
        tc += pred.confidence
    down, neutral, up = td / tw, tn / tw, tu / tw
    total = down + neutral + up or 1.0
    down, neutral, up = down / total, neutral / total, up / total

    direction = max([("down", down), ("neutral", neutral), ("up", up)], key=lambda x: x[1])[0]
    n = len(rows)
    avg_conf = tc / n

    # Důvěryhodnost: počet zpráv (max při 8+), průměrná confidence,
    # a vyhraněnost rozdělení (1 - normalizovaná entropie)
    probs = [p for p in (down, neutral, up) if p > 0]
    entropy = -sum(p * math.log(p) for p in probs) / math.log(3)
    trust = 100 * (0.35 * min(n / 8, 1.0) + 0.35 * avg_conf + 0.30 * (1 - entropy))

    return {
        "n_news": n,
        "prob_down": round(down, 4), "prob_neutral": round(neutral, 4), "prob_up": round(up, 4),
        "direction": direction,
        "trust_score": round(trust, 1),
        "avg_confidence": round(avg_conf, 3),
    }


async def ensure_snapshots(session: AsyncSession, tickers: list[Ticker]) -> int:
    """Po London open vytvoří denní snapshot BIASu (jednou za den a ticker)."""
    now = datetime.utcnow()
    tday = _trading_day(now)
    # Snapshot až po London open daného obchodního dne
    london = datetime.combine(tday, LONDON_OPEN_UTC)
    if now < london:
        return 0

    created = 0
    for ticker in tickers:
        existing = await session.scalar(
            select(DailyBias).where(DailyBias.ticker_id == ticker.id, DailyBias.bias_date == tday)
        )
        if existing:
            continue
        bias = await compute_bias(session, ticker, tday, until=london)
        session.add(DailyBias(
            ticker_id=ticker.id, bias_date=tday,
            prob_down=bias["prob_down"], prob_neutral=bias["prob_neutral"], prob_up=bias["prob_up"],
            direction=bias["direction"], trust_score=bias["trust_score"],
            n_news=bias["n_news"], avg_confidence=bias["avg_confidence"],
        ))
        created += 1
        log.info("Bias snapshot created", ticker=ticker.symbol, date=str(tday), **bias)
    if created:
        await session.commit()
    return created


async def evaluate_pending(session: AsyncSession, ticker_map: dict[int, Ticker]) -> int:
    """Doplhní realitu ke snapshotům po NY close (pohyb 07:00 -> 21:00 UTC)."""
    now = datetime.utcnow()
    today = _trading_day(now)
    stmt = select(DailyBias).where(DailyBias.realized_direction.is_(None)).limit(10)
    pending = (await session.execute(stmt)).scalars().all()

    yahoo = YahooFinanceAdapter()
    evaluated = 0
    for b in pending:
        # Hodnotit až po NY close daného dne
        if b.bias_date > today or (b.bias_date == today and now.time() < NY_CLOSE_UTC):
            continue
        ticker = ticker_map.get(b.ticker_id)
        if not ticker:
            continue
        try:
            bars = await asyncio.to_thread(yahoo.fetch_day_bars, ticker.symbol, b.bias_date)
            p_open = _find_close_at(bars, datetime.combine(b.bias_date, LONDON_OPEN_UTC, tzinfo=timezone.utc), 60)
            p_close = _find_close_at(bars, datetime.combine(b.bias_date, NY_CLOSE_UTC, tzinfo=timezone.utc), 60)
            if not p_open or not p_close:
                continue
            pct = (p_close - p_open) / p_open
            thr = ticker.neutral_threshold * 2  # celodenní pohyb — přísnější práh
            realized = "up" if pct > thr else ("down" if pct < -thr else "neutral")
            b.realized_direction = realized
            b.realized_pct = round(pct, 5)
            b.evaluated_at = now
            evaluated += 1
            log.info("Bias evaluated", ticker=ticker.symbol, date=str(b.bias_date),
                     bias=b.direction, realized=realized, pct=round(pct * 100, 2))
        except Exception as e:
            log.warning("Bias evaluation failed", ticker_id=b.ticker_id, error=str(e))
    if evaluated:
        await session.commit()
    return evaluated
