"""Denní BIAS endpointy — aktuální bias, snapshot a statistika úspěšnosti."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import DailyBias, Ticker
from app.repositories import TickerRepository
from app.routers.admin import _verify_token
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
            "ny_realized_direction": snapshot.ny_realized_direction,
            "ny_realized_pct": snapshot.ny_realized_pct,
            "v2_direction": snapshot.v2_direction,      # stínový bias v2 (na webu jen pro admina)
            "v2_cats": snapshot.v2_cats,
        },
        "live": live,
    }


@router.get("/outlook")
async def bias_outlook(
    ticker: str = Query(...),
    session: AsyncSession = Depends(get_session),
):
    """Pre-open výhled: dnešní US eventy + deterministické scénáře dopadu na instrument
    + krátký LLM narativ (cache 1×/den/instrument). Není investiční doporučení."""
    from datetime import date as _date
    from app.models import DailyOutlook
    from app.services.outlook_service import build_outlook, compute_scenario_stats
    from app.llm.client import llm_client

    t = await _get_ticker(session, ticker)
    tday = bias_service._trading_day(datetime.utcnow())

    outlook = await build_outlook(t.symbol, session)
    # Úspěšnost scénářů (1h reakce) — přiřaď každému scénáři dle jeho kategorie.
    stats = await compute_scenario_stats(session, t.symbol, days=90)
    for s in outlook["scenarios"]:
        s["stat"] = stats["by_category"].get(s.get("category"))
    outlook["scenario_stats"] = stats
    bias = await bias_service.compute_bias(session, t, tday)
    bias_ctx = {"direction": bias["direction"], "trust_score": bias["trust_score"],
                "prob_up": bias["prob_up"], "prob_down": bias["prob_down"],
                "prob_neutral": bias["prob_neutral"]}

    # Narativ: cache 1×/den/instrument (bounded cost i pro veřejný endpoint).
    cache_date = _date.fromisoformat(outlook["date"])
    cached = await session.scalar(
        select(DailyOutlook).where(DailyOutlook.ticker_id == t.id,
                                   DailyOutlook.outlook_date == cache_date)
    )
    if cached:
        narrative = cached.narrative
    else:
        narrative = llm_client.generate_outlook_narrative(t.symbol, outlook["scenarios"], bias_ctx)
        try:
            session.add(DailyOutlook(ticker_id=t.id, outlook_date=cache_date, narrative=narrative))
            await session.commit()
        except Exception:  # noqa: BLE001 — race: jiný request mezitím vložil týž řádek
            await session.rollback()

    return {**outlook, "bias": bias_ctx, "narrative": narrative}


@router.get("/gap")
async def bias_gap(ticker: str = Query(...)):
    """Dnešní RTH gap (přes ETF proxy) + historická pravděpodobnost zavření podle velikosti gapu.
    Směr NY session gap podle backtestu nepředpovídá — proto se ukazuje hlavně zavření."""
    import asyncio
    from app.services.gap_service import GAP_ETF, live_gap
    if ticker.upper() not in GAP_ETF:
        raise HTTPException(status_code=404, detail="Gap statistika je jen pro NQ, ES a YM")
    out = await asyncio.to_thread(live_gap, ticker)
    if out is None:
        raise HTTPException(status_code=503, detail="Data pro gap se nepodařilo načíst")
    return out


@router.get("/outlook/live/due", dependencies=[Depends(_verify_token)])
async def outlook_live_due():
    """Pro worker živých reakcí (Spark): které dnešní eventy právě sledovat."""
    from datetime import timezone
    from app.services.outlook_service import live_due_events
    from app.sources.forex_factory import get_upcoming_events
    now = datetime.now(timezone.utc)
    raw = await get_upcoming_events(window_before_min=10, window_after_min=90)
    return {"now": now.isoformat(), "events": live_due_events(raw, now)}


LIVE_TICKERS = {"EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD", "ES", "NQ", "YM"}


@router.post("/outlook/live/ingest", dependencies=[Depends(_verify_token)])
async def outlook_live_ingest(payload: dict, session: AsyncSession = Depends(get_session)):
    """{items: [{event_title, event_time_utc, ticker, proxy?, p0, points, last_pct, last_at}]} → upsert."""
    from app.models import OutlookLive
    n = 0
    for it in (payload.get("items") or [])[:200]:
        tk = str(it.get("ticker") or "").upper()
        if tk not in LIVE_TICKERS or not it.get("p0"):
            continue
        try:
            ev = datetime.fromisoformat(str(it["event_time_utc"]).replace("Z", "+00:00")).replace(tzinfo=None)
            last_at = (datetime.fromisoformat(str(it["last_at"]).replace("Z", "+00:00")).replace(tzinfo=None)
                       if it.get("last_at") else None)
        except (KeyError, ValueError):
            continue
        title = str(it.get("event_title") or "")[:200]
        points = {str(k): round(float(v), 5) for k, v in (it.get("points") or {}).items()
                  if str(k) in ("1", "5", "15", "30", "60") and v is not None}
        row = await session.scalar(select(OutlookLive).where(
            OutlookLive.event_date == ev.date(), OutlookLive.ticker == tk, OutlookLive.event_title == title))
        if row is None:
            row = OutlookLive(event_date=ev.date(), ticker=tk, event_title=title, event_time_utc=ev,
                              p0=float(it["p0"]))
            session.add(row)
        row.proxy = (str(it["proxy"])[:12] if it.get("proxy") else None)
        row.p0, row.points, row.last_at = float(it["p0"]), points, last_at
        row.last_pct = round(float(it["last_pct"]), 5) if it.get("last_pct") is not None else None
        n += 1
    await session.commit()
    return {"upserted": n}


@router.get("/outlook/stats")
async def bias_outlook_stats(
    ticker: str = Query(...),
    days: int = Query(default=90),
    session: AsyncSession = Depends(get_session),
):
    """Úspěšnost scénářů: predikovaný směr vs skutečný pohyb 1h po eventu, per kategorie."""
    from app.services.outlook_service import compute_scenario_stats
    t = await _get_ticker(session, ticker)
    return await compute_scenario_stats(session, t.symbol, days=days)


@router.post("/outlook/evaluate", dependencies=[Depends(_verify_token)])
async def outlook_evaluate(session: AsyncSession = Depends(get_session)):
    """Denní eval: uloží scénář vs realita pro dnešní vydané eventy. Volá cron."""
    from app.services.outlook_service import evaluate_outlook
    return await evaluate_outlook(session)


def _t_stat(xs: list[float]) -> float | None:
    if len(xs) < 5:
        return None
    m = sum(xs) / len(xs)
    sd = (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5
    return round(m / sd * len(xs) ** 0.5, 2) if sd else None


def _prop(k: int, n: int) -> dict:
    """Úspěšnost s 95% Wilsonovým intervalem; coin = interval obsahuje 50 % (neodlišitelné od náhody)."""
    import math
    if n <= 0:
        return {"k": 0, "n": 0, "pct": None, "ci": None, "coin": True}
    z, p = 1.96, k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    lo, hi = round(max(0.0, c - h) * 100, 1), round(min(1.0, c + h) * 100, 1)
    return {"k": k, "n": n, "pct": round(100 * p, 1), "ci": [lo, hi], "coin": lo <= 50 <= hi}


def _track(rows: list, dir_attr: str, real_attr: str) -> dict:
    """Směrové tipy (up/down) vs. směrová realita (up/down) — neutrální dny se nepočítají."""
    sel = [b for b in rows if getattr(b, dir_attr) in ("up", "down") and getattr(b, real_attr) in ("up", "down")]
    return _prop(sum(getattr(b, dir_attr) == getattr(b, real_attr) for b in sel), len(sel))


async def _track_record(session: AsyncSession, ticker_id: int) -> dict:
    """Celá historie (ne jen 30 dní): současný bias i stínový v2, NY session i London→close."""
    rows = [b for b in (await session.execute(
        select(DailyBias).where(DailyBias.ticker_id == ticker_id, DailyBias.realized_direction.is_not(None))
    )).scalars().all() if b.bias_date.weekday() < 5]
    days = [b.bias_date for b in rows]
    return {
        "since": str(min(days)) if days else None,
        "ny": _track(rows, "direction", "ny_realized_direction"),
        "london": _track(rows, "direction", "realized_direction"),
        "v2": {
            "ny": _track(rows, "v2_direction", "ny_realized_direction"),
            "london": _track(rows, "v2_direction", "realized_direction"),
            "signal_days": sum(b.v2_direction in ("up", "down") for b in rows),
            "days": sum(b.v2_direction is not None for b in rows),
        },
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

    # "unknown" (nešlo určit) se do úspěšnosti nepočítá — nebyl to výrok o směru.
    # Víkendové řádky (staré, z doby před opravou snapshotů) nejsou obchodní dny.
    rows = [b for b in rows if b.direction != "unknown" and b.bias_date.weekday() < 5]
    # Hlavní metrika = NY session (9:30 → 16:00 ET). London→close obsahuje i premarket/gap,
    # takže úspěšnost zkresluje (držíme ji jen pro srovnání jako *_london).
    ny_rows = [b for b in rows if b.ny_realized_direction is not None]
    total = len(ny_rows)
    correct = sum(1 for b in ny_rows if b.direction == b.ny_realized_direction)
    # Úspěšnost směrových biasů (bez neutral predikcí) — to tradera zajímá nejvíc
    directional = [b for b in rows if b.direction in ("up", "down")]
    ny_directional = [b for b in ny_rows if b.direction in ("up", "down")]
    dir_correct = sum(1 for b in ny_directional if b.direction == b.ny_realized_direction)
    lon_dir_correct = sum(1 for b in directional if b.direction == b.realized_direction)

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
        # Průkaznost: t = průměr / směrodatná odchylka × √n. |t| < 2 = zatím jen šum.
        "t_stat": _t_stat(entry_pnls),
        "since": str(min(b.bias_date for b in filled)) if filled else None,
    }

    return {
        "ticker": t.symbol,
        "days": days,
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else None,
        "directional_total": len(ny_directional),
        "directional_correct": dir_correct,
        "directional_accuracy": round(dir_correct / len(ny_directional), 4) if ny_directional else None,
        "metric": "ny_session",
        "directional_total_london": len(directional),
        "directional_accuracy_london": round(lon_dir_correct / len(directional), 4) if directional else None,
        "entry": entry,
        # Skutečná historická úspěšnost s intervalem (nahrazuje „důvěryhodnost“ trust score, která
        # se ukázala jako antikorelovaná s úspěšností — rozbor 11/2026). v2 = stínový bias.
        "track": await _track_record(session, t.id),
        "history": [
            {
                "date": str(b.bias_date),
                "bias": b.direction,
                "realized": b.ny_realized_direction,
                "correct": b.direction == b.ny_realized_direction if b.ny_realized_direction else None,
                "trust_score": b.trust_score,
                "realized_pct": b.ny_realized_pct,
                "realized_london": b.realized_direction,
                "realized_pct_london": b.realized_pct,
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
        "ny_open_utc": bias_service.ny_open_utc(tday).strftime("%H:%M"),   # 13:30 v létě, 14:30 v zimě
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
    v2 = await bias_service.fill_v2_missing(session)
    evaluated = await bias_service.evaluate_pending(session, {t.id: t for t in tickers})
    return {"snapshots_created": created, "v2_filled": v2, "evaluated": evaluated}
