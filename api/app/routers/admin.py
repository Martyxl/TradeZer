import os

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.schemas import RefreshResponse
from app.services.news_aggregator import NewsAggregator

router = APIRouter(prefix="/api", tags=["admin"])


def _verify_token(
    x_internal_token: str = Header(default=""),
    authorization: str = Header(default=""),
):
    # Accept X-Internal-Token (manual calls, cron-job.org)
    if settings.internal_api_token and x_internal_token == settings.internal_api_token:
        return
    # Accept Vercel cron: Authorization: Bearer <CRON_SECRET>
    cron_secret = os.environ.get("CRON_SECRET", "")
    if cron_secret and authorization == f"Bearer {cron_secret}":
        return
    # Reject if token is configured but nothing matched
    if settings.internal_api_token:
        raise HTTPException(status_code=401, detail="Neplatný token")


@router.post("/refresh", response_model=RefreshResponse, dependencies=[Depends(_verify_token)])
async def manual_refresh(
    session: AsyncSession = Depends(get_session),
    max_predictions: int = Query(default=8, ge=1, le=50),
):
    aggregator = NewsAggregator(session)
    stats = await aggregator.refresh(max_predictions=max_predictions)
    return RefreshResponse(status="ok", stats=stats)


@router.post("/predict", dependencies=[Depends(_verify_token)])
async def predict_pending(
    session: AsyncSession = Depends(get_session),
    max_predictions: int = Query(default=8, ge=1, le=30),
):
    """Spustí LLM predikce pro položky bez predikcí (bez RSS fetche — rychlejší)."""
    aggregator = NewsAggregator(session)
    stats = await aggregator.predict_pending(max_predictions=max_predictions)
    return {"status": "ok", "stats": stats}


@router.post("/calibrate", dependencies=[Depends(_verify_token)])
async def calibrate(
    session: AsyncSession = Depends(get_session),
):
    """Stáhne tržní ceny a zaznamená market reactions pro predikce starší 15 min."""
    from app.services.calibration_service import CalibrationService
    service = CalibrationService(session)
    stats = await service.run()
    return {"status": "ok", "stats": stats}


@router.get("/reactions/analysis", dependencies=[Depends(_verify_token)])
async def reactions_analysis(
    ticker: str = Query(default="EURUSD"),
    days: int = Query(default=90),
    session: AsyncSession = Depends(get_session),
):
    """Vrátí distribuci pct_change_15m pro daný ticker — pro kalibraci neutral_threshold."""
    from sqlalchemy import select, func as sqlfunc
    from app.models import MarketReaction, NewsItem
    from app.repositories import TickerRepository
    from datetime import datetime, timedelta

    ticker_repo = TickerRepository(session)
    ticker_obj = await ticker_repo.get_by_symbol(ticker)
    if not ticker_obj:
        return {"error": "ticker not found"}

    cutoff = datetime.utcnow() - timedelta(days=days)
    stmt = (
        select(MarketReaction.pct_change_15m, MarketReaction.realized_direction)
        .join(NewsItem, NewsItem.id == MarketReaction.news_id)
        .where(
            MarketReaction.ticker_id == ticker_obj.id,
            MarketReaction.pct_change_15m.isnot(None),
            NewsItem.published_at >= cutoff,
        )
        .order_by(MarketReaction.pct_change_15m)
    )
    result = await session.execute(stmt)
    rows = result.all()

    if not rows:
        return {"ticker": ticker, "count": 0, "message": "no data"}

    pcts = [abs(r.pct_change_15m) * 100 for r in rows]  # abs, v procentech
    raw_pcts = [round(r.pct_change_15m * 100, 4) for r in rows]

    pcts.sort()
    n = len(pcts)
    percentiles = {
        "p10": round(pcts[int(n * 0.10)], 4),
        "p25": round(pcts[int(n * 0.25)], 4),
        "p50": round(pcts[n // 2], 4),
        "p75": round(pcts[int(n * 0.75)], 4),
        "p90": round(pcts[int(n * 0.90)], 4),
        "p95": round(pcts[int(n * 0.95)], 4),
        "p99": round(pcts[min(int(n * 0.99), n - 1)], 4),
    }
    avg = round(sum(pcts) / n, 4)
    current_threshold = round(ticker_obj.neutral_threshold * 100, 4)

    # Kolik vzorků by bylo classified jako non-neutral při různých thresholdech
    thresholds_test = [0.01, 0.02, 0.03, 0.04, 0.05, 0.07, 0.10, 0.15, 0.20]
    threshold_sim = {
        f"{t*100:.0f}bp": {
            "non_neutral_count": sum(1 for p in pcts if p > t * 100),
            "non_neutral_pct": round(sum(1 for p in pcts if p > t * 100) / n * 100, 1),
        }
        for t in thresholds_test
    }

    return {
        "ticker": ticker,
        "current_threshold_pct": current_threshold,
        "count": n,
        "abs_pct_change_15m": {
            "avg": avg,
            "min": round(pcts[0], 4),
            "max": round(pcts[-1], 4),
            **percentiles,
        },
        "raw_sample_20": raw_pcts[:20],
        "threshold_simulation": threshold_sim,
    }


@router.patch("/tickers/{symbol}/threshold", dependencies=[Depends(_verify_token)])
async def update_threshold(
    symbol: str,
    threshold: float = Query(description="Nový neutral_threshold jako frakce (0.0005 = 0.05%)"),
    session: AsyncSession = Depends(get_session),
):
    """Aktualizuje neutral_threshold pro ticker. Po změně spusť /api/calibrate znovu."""
    from app.repositories import TickerRepository

    repo = TickerRepository(session)
    ticker = await repo.get_by_symbol(symbol.upper())
    if not ticker:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Ticker {symbol} not found")

    from sqlalchemy import update
    from app.models import MarketReaction

    old = ticker.neutral_threshold
    ticker.neutral_threshold = threshold

    # Reset realized_direction na NULL → calibrate je přepočítá s novým prahem
    reset_stmt = (
        update(MarketReaction)
        .where(MarketReaction.ticker_id == ticker.id)
        .values(realized_direction=None)
    )
    result = await session.execute(reset_stmt)
    reset_count = result.rowcount
    await session.commit()

    return {
        "symbol": symbol.upper(),
        "old_threshold": old,
        "new_threshold": threshold,
        "old_pct": round(old * 100, 4),
        "new_pct": round(threshold * 100, 4),
        "reactions_reset": reset_count,
        "message": "Threshold aktualizován, realized_direction resetován — zavolej /api/calibrate",
    }


@router.get("/health")
async def health():
    return {"status": "ok", "version": "1.1.0"}
