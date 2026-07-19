"""Denní BIAS endpointy — aktuální bias, snapshot a statistika úspěšnosti."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import DailyBias, Ticker
from app.repositories import TickerRepository
from app.services import bias_service

router = APIRouter(prefix="/api/bias", tags=["bias"])


async def _get_ticker(session: AsyncSession, symbol: str) -> Ticker:
    ticker = await session.scalar(select(Ticker).where(Ticker.symbol == symbol.upper()))
    if not ticker:
        raise HTTPException(status_code=404, detail=f"Ticker {symbol} nenalezen")
    return ticker


@router.get("/today")
async def bias_today(
    ticker: str = Query(...),
    session: AsyncSession = Depends(get_session),
):
    """Snapshot BIASu (London open) + živý přepočet z aktuálních zpráv."""
    t = await _get_ticker(session, ticker)
    tday = bias_service._trading_day(datetime.utcnow())

    snapshot = await session.scalar(
        select(DailyBias).where(DailyBias.ticker_id == t.id, DailyBias.bias_date == tday)
    )
    live = await bias_service.compute_bias(session, t, tday)

    return {
        "ticker": t.symbol,
        "date": str(tday),
        "snapshot": None if not snapshot else {
            "prob_down": snapshot.prob_down,
            "prob_neutral": snapshot.prob_neutral,
            "prob_up": snapshot.prob_up,
            "direction": snapshot.direction,
            "trust_score": snapshot.trust_score,
            "n_news": snapshot.n_news,
            "snapshot_at": str(snapshot.snapshot_at)[:16],
            "realized_direction": snapshot.realized_direction,
            "realized_pct": snapshot.realized_pct,
        },
        "live": live,
    }


@router.get("/stats")
async def bias_stats(
    ticker: str = Query(...),
    days: int = Query(default=30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
):
    """Úspěšnost BIASu za posledních N dní (jen vyhodnocené snapshoty)."""
    from datetime import timedelta, date as date_type

    t = await _get_ticker(session, ticker)
    cutoff = date_type.today() - timedelta(days=days)
    rows = (await session.execute(
        select(DailyBias)
        .where(DailyBias.ticker_id == t.id)
        .where(DailyBias.bias_date >= cutoff)
        .where(DailyBias.realized_direction.is_not(None))
        .order_by(DailyBias.bias_date.desc())
    )).scalars().all()

    total = len(rows)
    correct = sum(1 for b in rows if b.direction == b.realized_direction)
    # Úspěšnost směrových biasů (bez neutral predikcí) — to tradera zajímá nejvíc
    directional = [b for b in rows if b.direction in ("up", "down")]
    dir_correct = sum(1 for b in directional if b.direction == b.realized_direction)

    return {
        "ticker": t.symbol,
        "days": days,
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else None,
        "directional_total": len(directional),
        "directional_correct": dir_correct,
        "directional_accuracy": round(dir_correct / len(directional), 4) if directional else None,
        "history": [
            {
                "date": str(b.bias_date),
                "bias": b.direction,
                "realized": b.realized_direction,
                "correct": b.direction == b.realized_direction,
                "trust_score": b.trust_score,
                "realized_pct": b.realized_pct,
            }
            for b in rows[:60]
        ],
    }


@router.post("/run")
async def bias_run(session: AsyncSession = Depends(get_session)):
    """Ruční trigger snapshotu + vyhodnocení (jinak běží po refreshi)."""
    ticker_repo = TickerRepository(session)
    tickers = list(await ticker_repo.get_all_enabled())
    created = await bias_service.ensure_snapshots(session, tickers)
    evaluated = await bias_service.evaluate_pending(session, {t.id: t for t in tickers})
    return {"snapshots_created": created, "evaluated": evaluated}
