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

    # "unknown" (nešlo určit) se do úspěšnosti nepočítá — nebyl to výrok o směru
    rows = [b for b in rows if b.direction != "unknown"]
    total = len(rows)
    correct = sum(1 for b in rows if b.direction == b.realized_direction)
    # Úspěšnost směrových biasů (bez neutral predikcí) — to tradera zajímá nejvíc
    directional = [b for b in rows if b.direction in ("up", "down")]
    dir_correct = sum(1 for b in directional if b.direction == b.realized_direction)

    # Úspěšnost entry plánu (jen dny, kde limit fillnul)
    filled = [b for b in directional if b.entry_filled]
    entry_wins = [b for b in filled if b.entry_win]
    entry_pnls = [b.entry_pnl_pct for b in filled if b.entry_pnl_pct is not None]
    entry = {
        "directional_days": len(directional),
        "filled": len(filled),
        "fill_rate": round(len(filled) / len(directional), 4) if directional else None,
        "wins": len(entry_wins),
        "win_rate": round(len(entry_wins) / len(filled), 4) if filled else None,
        "avg_pnl_pct": round(sum(entry_pnls) / len(entry_pnls), 3) if entry_pnls else None,
        "sum_pnl_pct": round(sum(entry_pnls), 2) if entry_pnls else None,
    }

    return {
        "ticker": t.symbol,
        "days": days,
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else None,
        "directional_total": len(directional),
        "directional_correct": dir_correct,
        "directional_accuracy": round(dir_correct / len(directional), 4) if directional else None,
        "entry": entry,
        "history": [
            {
                "date": str(b.bias_date),
                "bias": b.direction,
                "realized": b.realized_direction,
                "correct": b.direction == b.realized_direction,
                "trust_score": b.trust_score,
                "realized_pct": b.realized_pct,
                "entry_filled": b.entry_filled,
                "entry_win": b.entry_win,
                "entry_pnl_pct": b.entry_pnl_pct,
            }
            for b in rows[:60]
        ],
    }


@router.get("/entry")
async def bias_entry(
    ticker: str = Query(...),
    session: AsyncSession = Depends(get_session),
):
    """Odhad ideálního entry po NY open pro dnešní směr biasu.

    Kombinuje: dnešní bias směr + reálné agregáty NY-cesty (jak se sbírají)
    a slouží jako doplněk statického playbooku z /stats (ny_entry).
    """
    from statistics import median

    t = await _get_ticker(session, ticker)
    tday = bias_service._trading_day(datetime.utcnow())
    snap = await session.scalar(
        select(DailyBias).where(DailyBias.ticker_id == t.id, DailyBias.bias_date == tday)
    )
    live = await bias_service.compute_bias(session, t, tday)
    direction = (snap.direction if snap else live["direction"])

    # Reálné agregáty NY-cesty za posledních 90 dní pro daný směr biasu
    rows = (await session.execute(
        select(DailyBias)
        .where(DailyBias.ticker_id == t.id)
        .where(DailyBias.direction == direction)
        .where(DailyBias.ny_adverse_pct.is_not(None))
    )).scalars().all()

    realized = None
    if rows:
        adv = [r.ny_adverse_pct for r in rows]
        fav = [r.ny_favorable_pct for r in rows if r.ny_favorable_pct is not None]
        mins = [r.ny_adverse_min for r in rows if r.ny_adverse_min is not None]
        realized = {
            "n": len(rows),
            "offset_pct": round(median(adv), 3),
            "favorable_pct": round(median(fav), 3) if fav else None,
            "median_min": int(median(mins)) if mins else None,
        }

    return {
        "ticker": t.symbol,
        "date": str(tday),
        "direction": direction,
        "ny_open_utc": "13:30",
        "realized": realized,  # z reálných biasů (roste časem)
        "note": "Playbook z historických dat je v /stats (ny_entry). "
                "'realized' je z reálně zaznamenaných biasů.",
    }


@router.post("/run")
async def bias_run(session: AsyncSession = Depends(get_session)):
    """Ruční trigger snapshotu + vyhodnocení (jinak běží po refreshi)."""
    ticker_repo = TickerRepository(session)
    tickers = list(await ticker_repo.get_all_enabled())
    created = await bias_service.ensure_snapshots(session, tickers)
    evaluated = await bias_service.evaluate_pending(session, {t.id: t for t in tickers})
    return {"snapshots_created": created, "evaluated": evaluated}
