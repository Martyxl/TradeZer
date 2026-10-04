"""Valuation Radar API. Konvence repa: /api/valuation, bez verzování.

Čte jen z DB (žádné volání providerů z request pathu). Každá response nese
meta (as_of_date, model_version, data_source, disclaimer).
"""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import date, timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.db import get_session
from app.models import InvestmentTx, User
from app.routers.admin import _verify_token
from app.routers.auth import require_plan, current_user
from app.valuation import schemas as S

log = structlog.get_logger(__name__)

# Placené moduly: Valuation Radar je od plánu Trader výš (server-side gate).
_TRADER = [Depends(require_plan("trader"))]
from app.valuation.models import (
    ValGroup, ValInstrument, ValScoreDaily, ValMetricsDaily,
    ValFinancials, ValEstimate, ValEarningsHistory, ValScoreRun, ValPriceDaily,
    ValOverviewSnapshot,
)
from app.valuation.scoring_config import CONF_UNRELIABLE

router = APIRouter(prefix="/api/valuation", tags=["valuation"])


def _meta(as_of: date | None) -> S.Meta:
    return S.Meta(as_of_date=as_of, model_version=settings.val_model_version,
                  data_source=settings.market_data_provider)


async def _latest_score_date(session: AsyncSession) -> date | None:
    return await session.scalar(
        select(func.max(ValScoreDaily.as_of_date)).where(
            ValScoreDaily.model_version == settings.val_model_version)
    )


_sec_tickers_cache: dict = {"data": None, "ts": 0.0}


def _load_sec_tickers() -> dict:
    """SEC mapa ticker→název (cache 24 h). Blokující — volat přes threadpool."""
    now = time.time()
    if _sec_tickers_cache["data"] and now - _sec_tickers_cache["ts"] < 86400:
        return _sec_tickers_cache["data"]
    try:
        req = urllib.request.Request("https://www.sec.gov/files/company_tickers.json",
                                     headers={"User-Agent": settings.sec_user_agent})
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = json.loads(r.read().decode())
        data = {str(v["ticker"]).upper(): (v.get("title") or "")
                for v in raw.values() if v.get("ticker")}
        _sec_tickers_cache.update(data=data, ts=now)
        return data
    except Exception as e:  # noqa: BLE001
        log.warning("SEC tickers fetch fail", error=str(e))
        return _sec_tickers_cache["data"] or {}


def _resolve_ticker(query: str) -> tuple[str, str] | None:
    """Z dotazu (ticker nebo název firmy) vrátí (ticker, název) přes SEC mapu."""
    q = query.strip()
    if not q:
        return None
    m = _load_sec_tickers()
    up = q.upper()
    if up in m:
        return up, m[up]
    ql = q.lower()
    matches = [(t, n) for t, n in m.items() if ql in n.lower()]
    if matches:
        matches.sort(key=lambda x: len(x[1]))  # nejkratší název = nejpřesnější
        return matches[0]
    return None


async def _held_tickers(session: AsyncSession, user_id: int) -> set[str]:
    """Tickery, které uživatel reálně drží (net > 0), vč. base bez burz. suffixu."""
    rows = (await session.execute(
        select(InvestmentTx.symbol, InvestmentTx.tx_type, InvestmentTx.quantity).where(
            InvestmentTx.user_id == user_id, InvestmentTx.symbol.isnot(None),
            InvestmentTx.tx_type.in_(("buy", "sell"))))).all()
    net: dict[str, float] = {}
    for sym, tt, qty in rows:
        net[sym] = net.get(sym, 0) + (qty or 0) * (1 if tt == "buy" else -1)
    held = set()
    for sym, v in net.items():
        if v > 1e-9:
            held.add(sym.upper())
            held.add(sym.split(".")[0].upper())  # OGN.US → OGN (valuation má plain)
    return held


# ---- static routes (před dynamickým /{ticker}) ------------------------------

@router.get("/groups", response_model=S.GroupsResponse, dependencies=_TRADER)
async def groups(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(ValGroup).order_by(ValGroup.sort_order))).scalars().all()
    return S.GroupsResponse(
        meta=_meta(None),
        groups=[S.GroupOut(key=g.key, label_cs=g.label_cs, label_en=g.label_en,
                           color_hex=g.color_hex, sort_order=g.sort_order) for g in rows],
    )


@router.get("/universe", dependencies=[Depends(_verify_token)])
async def universe(session: AsyncSession = Depends(get_session)):
    """Seznam display tickerů (interní token) — pro cenový backfill scanner na Sparku,
    aby pokrýval všechny zobrazované firmy a percentil nestárl."""
    rows = (await session.execute(
        select(ValInstrument.ticker).where(
            ValInstrument.in_display_universe == True,  # noqa: E712
            ValInstrument.active == True)  # noqa: E712
        .order_by(ValInstrument.ticker))).scalars().all()
    return {"tickers": list(rows)}


@router.post("/request")
async def request_ticker(payload: dict, user: User = Depends(current_user),
                         session: AsyncSession = Depends(get_session)):
    """Přidání akcie na přání: zákazník zadá ticker/název → přidá se do seznamu
    (community) + počítadlo požadavků + best-effort SEC výpočet (jinak dopočítá Spark)."""
    query = (payload.get("query") or payload.get("ticker") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Zadej ticker nebo název firmy.")
    resolved = await run_in_threadpool(_resolve_ticker, query)
    if not resolved:
        raise HTTPException(status_code=404, detail="Firma nenalezena. Zkus přesný ticker (např. AAPL).")
    ticker, name = resolved

    # zajisti community skupinu (FK)
    if await session.scalar(select(ValGroup).where(ValGroup.key == "community")) is None:
        session.add(ValGroup(key="community", label_cs="Na přání", label_en="Community",
                             color_hex="#9184d9", sort_order=99))
        await session.commit()

    inst = await session.get(ValInstrument, ticker)
    newly = inst is None
    if inst is None:
        inst = ValInstrument(ticker=ticker, name=name, group_key="community",
                             in_display_universe=True, in_peer_universe=True, active=True, request_count=1)
        session.add(inst)
    else:
        inst.request_count = (inst.request_count or 0) + 1
        inst.in_display_universe = True
        if not inst.name:
            inst.name = name
    await session.commit()

    # Best-effort okamžitý výpočet (1 ticker se do 60 s vejde; chyba nevadí → dopočítá Spark).
    computed = False
    try:
        from app.valuation.ingest import ingest_all
        from app.valuation.compute import compute_all
        from app.valuation.score import score_all
        await ingest_all(session, tickers=[ticker], force=False, provider_name="sec")
        await compute_all(session, tickers=[ticker])
        r = await score_all(session, tickers=[ticker])
        computed = bool(r.get("scored"))
        await build_overview_snapshot(session)  # nová firma hned v overview snapshotu
    except Exception as e:  # noqa: BLE001
        log.warning("request ticker ingest best-effort fail", ticker=ticker, error=str(e))

    return {"status": "ok", "ticker": ticker, "name": name, "newly_added": newly,
            "computed": computed, "request_count": inst.request_count}


async def _compute_overview_rows(session: AsyncSession) -> tuple[date | None, list[dict]]:
    """TĚŽKÝ výpočet (celé tabulky skóre+metrik) → plný seznam položek overview bez
    filtrů. Volá se jen při stavbě snapshotu, NE v hot pathu requestu."""
    version = settings.val_model_version
    all_scores = (await session.execute(select(ValScoreDaily).where(
        ValScoreDaily.model_version == version).order_by(ValScoreDaily.as_of_date.desc()))).scalars().all()
    latest_score: dict[str, ValScoreDaily] = {}
    for s in all_scores:
        latest_score.setdefault(s.ticker, s)
    if not latest_score:
        return None, []
    all_metrics = (await session.execute(select(ValMetricsDaily).where(
        ValMetricsDaily.model_version == version).order_by(ValMetricsDaily.as_of_date.desc()))).scalars().all()
    metrics: dict[str, dict] = {}
    for mr in all_metrics:
        metrics.setdefault(mr.ticker, mr.metrics)
    instruments = {i.ticker: i for i in (await session.execute(
        select(ValInstrument).where(ValInstrument.in_display_universe == True))).scalars().all()}  # noqa: E712
    as_of = max(s.as_of_date for s in latest_score.values())
    rows: list[dict] = []
    for ticker, s in latest_score.items():
        inst = instruments.get(ticker)
        if inst is None:
            continue
        m = metrics.get(ticker, {})
        rows.append({
            "ticker": s.ticker, "name": inst.name, "group_key": inst.group_key,
            "pctile_pe_fwd": m.get("pctile_pe_fwd"),
            "eps_growth_ntm": m.get("eps_growth_ntm") if m.get("eps_growth_ntm") is not None else m.get("eps_yoy_ttm"),
            "market_cap": m.get("market_cap"), "valuation_score": s.valuation_score,
            "composite_score": s.composite_score, "valuation_verdict": s.valuation_verdict,
            "horizon_verdict": s.horizon_verdict, "bubble_flag": s.bubble_flag, "confidence": s.confidence,
        })
    rows.sort(key=lambda x: (x["composite_score"] if x["composite_score"] is not None else -1), reverse=True)
    return as_of, rows


async def build_overview_snapshot(session: AsyncSession) -> int:
    """Postaví/aktualizuje předpočítaný overview blob (name='latest'). Vrací počet položek."""
    as_of, rows = await _compute_overview_rows(session)
    snap = await session.get(ValOverviewSnapshot, "latest")
    payload = {"items": rows}
    if snap is None:
        session.add(ValOverviewSnapshot(name="latest", as_of_date=as_of, payload=payload))
    else:
        snap.as_of_date = as_of
        snap.payload = payload
    await session.commit()
    return len(rows)


@router.get("/overview", response_model=S.OverviewResponse)
async def overview(
    group: str | None = Query(default=None),
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
    portfolio: bool = Query(default=False, description="Jen tituly z portfolia uživatele"),
    user: User = Depends(require_plan("trader")),
    session: AsyncSession = Depends(get_session),
):
    # Hot path = čtení předpočítaného blobu (ne celé tabulky). Filtry v Pythonu nad
    # malým seznamem. První běh / po deployi snapshot chybí → postaví se (fallback).
    snap = await session.get(ValOverviewSnapshot, "latest")
    if snap is None:
        await build_overview_snapshot(session)
        snap = await session.get(ValOverviewSnapshot, "latest")
    if snap is None:
        return S.OverviewResponse(meta=_meta(None), items=[])

    rows = (snap.payload or {}).get("items", [])
    held = await _held_tickers(session, user.id) if portfolio else None
    items = []
    for r in rows:
        if held is not None and (r.get("ticker") or "").upper() not in held:
            continue
        if group and r.get("group_key") != group:
            continue
        if (r.get("confidence") or 0) < min_confidence:
            continue
        items.append(S.OverviewItem(**r))
    return S.OverviewResponse(meta=_meta(snap.as_of_date), items=items)


@router.post("/refresh", response_model=S.RefreshResponse, dependencies=[Depends(_verify_token)])
async def refresh(
    with_ingest: bool = Query(default=False, description="Zahrne i ingest (pomalé, jen mimo Vercel)"),
    tickers: str | None = Query(default=None, description="CSV omezení tickerů (jinak celé peer univerzum)"),
    force: bool = Query(default=False, description="Vynutí re-fetch (obejde dnešní cache)"),
    provider: str | None = Query(default=None, description="Override providera pro tento běh (sec/fmp/yfinance)"),
    session: AsyncSession = Depends(get_session),
):
    """Přepočte metriky a skóre z DB. with_ingest=true navíc stáhne data
    (na Vercelu se do 60s nevejde celé univerzum — pro plný ingest použij CLI/cron)."""
    from app.valuation.compute import compute_all
    from app.valuation.score import score_all

    stages: dict[str, dict] = {}
    tick_list = [t.strip().upper() for t in tickers.split(",")] if tickers else None
    if with_ingest:
        from app.valuation.ingest import ingest_all
        stages["ingest"] = await ingest_all(session, tickers=tick_list, force=force, provider_name=provider)
    # Když je zadán ticker list, scope i compute/score (jinak by přepočet přes celé
    # univerzum přetáhl 60s Vercel limit).
    stages["compute"] = await compute_all(session, tickers=tick_list)
    score_stats = await score_all(session, tickers=tick_list)
    stages["score"] = score_stats
    stages["overview_snapshot"] = {"items": await build_overview_snapshot(session)}
    return S.RefreshResponse(meta=_meta(await _latest_score_date(session)),
                             status="ok", run_id=score_stats.get("run_id"), stages=stages)


def _f(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


@router.post("/prices/ingest", dependencies=[Depends(_verify_token)])
async def prices_ingest(payload: dict, session: AsyncSession = Depends(get_session)):
    """Přijme externě natažené denní ceny (lokální Yahoo backfill / n8n) a upsertne do
    ValPriceDaily. Řeší mezeru, kde FMP free nedává hlubokou historii pro některé firmy.

    Body: {"ticker":"LLY","bars":[{"date":"2015-08-11","open":..,"high":..,"low":..,
    "close":..,"adj_close":..,"volume":..}, ...]}. Vkládá jen chybějící data
    (idempotentní). Přepočet metrik/skóre zvlášť přes POST /refresh?tickers=...
    (with_ingest=false), aby percentil viděl doplněnou historii.
    """
    ticker = (payload.get("ticker") or "").strip().upper()
    bars = payload.get("bars")
    if not ticker or not isinstance(bars, list):
        raise HTTPException(status_code=400, detail="Očekávám body {ticker, bars:[...]}")
    existing = set(await session.scalars(
        select(ValPriceDaily.date).where(ValPriceDaily.ticker == ticker)))
    new_rows, seen = [], set()
    for b in bars:
        raw = (b.get("date") or "")[:10]
        try:
            d = date.fromisoformat(raw)
        except (ValueError, TypeError):
            continue
        if d in existing or d in seen:
            continue
        seen.add(d)
        close = _f(b.get("close"))
        new_rows.append(ValPriceDaily(
            ticker=ticker, date=d, open=_f(b.get("open")), high=_f(b.get("high")),
            low=_f(b.get("low")), close=close,
            adj_close=(_f(b.get("adj_close")) if b.get("adj_close") is not None else close),
            volume=_f(b.get("volume"))))
    if new_rows:
        session.add_all(new_rows)
        await session.commit()
    total = await session.scalar(
        select(func.count()).select_from(ValPriceDaily).where(ValPriceDaily.ticker == ticker))
    return {"status": "ok", "ticker": ticker, "received": len(bars),
            "inserted": len(new_rows), "total_in_db": total}


@router.post("/instruments", dependencies=[Depends(_verify_token)])
async def upsert_instruments(payload: dict, session: AsyncSession = Depends(get_session)):
    """Přidá/aktualizuje instrumenty (ticker list) do dané skupiny + display/peer.

    Body: {"tickers": ["MRK","OGN",...], "group_key": "healthcare", "display": true}
    """
    tickers = [t.strip().upper() for t in payload.get("tickers", []) if t.strip()]
    group_key = payload.get("group_key")
    display = bool(payload.get("display", True))
    added = updated = 0
    for t in tickers:
        inst = await session.get(ValInstrument, t)
        if inst is None:
            session.add(ValInstrument(ticker=t, group_key=group_key,
                                      in_display_universe=display, in_peer_universe=True, active=True))
            added += 1
        else:
            inst.in_display_universe = display
            inst.in_peer_universe = True
            if group_key:
                inst.group_key = group_key
            updated += 1
    await session.commit()
    return {"status": "ok", "added": added, "updated": updated, "tickers": tickers}


@router.post("/seed", dependencies=[Depends(_verify_token)])
async def seed(session: AsyncSession = Depends(get_session)):
    """Naplní val_groups + val_instruments (běžící DB se přes app.db.seed neplní)."""
    from app.db.seed_valuation import seed_valuation
    stats = await seed_valuation(session)
    return {"status": "ok", **stats}


@router.get("/runs/{run_id}", response_model=S.RunOut, dependencies=_TRADER)
async def get_run(run_id: int, session: AsyncSession = Depends(get_session)):
    run = await session.scalar(select(ValScoreRun).where(ValScoreRun.id == run_id))
    if not run:
        raise HTTPException(status_code=404, detail="Run nenalezen")
    return S.RunOut(
        meta=_meta(None), run_id=run.id,
        started_at=str(run.started_at) if run.started_at else None,
        finished_at=str(run.finished_at) if run.finished_at else None,
        tickers_ok=run.tickers_ok, tickers_failed=run.tickers_failed, notes=run.notes,
    )


@router.get("/backtest", dependencies=_TRADER)
async def backtest(session: AsyncSession = Depends(get_session)):
    """Skóre vs. budoucí výnos (1M/3M). Roste s historií skóre."""
    from app.valuation.backtest import run_backtest
    result = await run_backtest(session)
    return {"meta": _meta(await _latest_score_date(session)).model_dump(), **result}


# ---- dynamické routes -------------------------------------------------------

@router.get("/{ticker}/summary", dependencies=_TRADER)
async def ticker_summary(ticker: str, session: AsyncSession = Depends(get_session)):
    """LLM shrnutí nad spočítanými čísly (cache 24 h). Prázdné, když LLM nedostupné."""
    from app.valuation.summary import get_summary
    result = await get_summary(session, ticker)
    return {"meta": _meta(None).model_dump(), **result}


@router.get("/{ticker}/history", response_model=S.HistoryResponse, dependencies=_TRADER)
async def ticker_history(
    ticker: str, days: int = Query(default=365, ge=1, le=1825),
    session: AsyncSession = Depends(get_session),
):
    ticker = ticker.upper()
    cutoff = date.today() - timedelta(days=days)
    rows = (await session.execute(
        select(ValScoreDaily).where(
            ValScoreDaily.ticker == ticker, ValScoreDaily.as_of_date >= cutoff,
            ValScoreDaily.model_version == settings.val_model_version)
        .order_by(ValScoreDaily.as_of_date.asc()))).scalars().all()
    return S.HistoryResponse(
        meta=_meta(rows[-1].as_of_date if rows else None), ticker=ticker,
        points=[S.HistoryPoint(as_of_date=r.as_of_date, valuation_score=r.valuation_score,
                               composite_score=r.composite_score, confidence=r.confidence,
                               bubble_flag=r.bubble_flag) for r in rows],
    )


@router.get("/{ticker}", response_model=S.ValuationDetail, dependencies=_TRADER)
async def ticker_detail(ticker: str, session: AsyncSession = Depends(get_session)):
    ticker = ticker.upper()
    version = settings.val_model_version
    inst = await session.scalar(select(ValInstrument).where(ValInstrument.ticker == ticker))
    score = await session.scalar(select(ValScoreDaily).where(
        ValScoreDaily.ticker == ticker, ValScoreDaily.model_version == version)
        .order_by(ValScoreDaily.as_of_date.desc()).limit(1))
    if inst is None and score is None:
        raise HTTPException(status_code=404, detail=f"Ticker {ticker} nenalezen")

    as_of = score.as_of_date if score else None
    metrics = {}
    if as_of:
        mrow = await session.scalar(select(ValMetricsDaily).where(
            ValMetricsDaily.ticker == ticker, ValMetricsDaily.as_of_date == as_of,
            ValMetricsDaily.model_version == version))
        metrics = mrow.metrics if mrow else {}

    fins = (await session.execute(select(ValFinancials).where(
        ValFinancials.ticker == ticker, ValFinancials.period_type == "Q")
        .order_by(ValFinancials.period_end.desc(), ValFinancials.revision_no.desc()).limit(4))).scalars().all()
    ests = (await session.execute(select(ValEstimate).where(ValEstimate.ticker == ticker)
        .order_by(ValEstimate.as_of_date.desc()).limit(8))).scalars().all()
    earn = (await session.execute(select(ValEarningsHistory).where(ValEarningsHistory.ticker == ticker)
        .order_by(ValEarningsHistory.period_end.desc()).limit(4))).scalars().all()

    drivers = {}
    if score and score.drivers:
        drivers = {k: [S.DriverItem(**d) for d in v] for k, v in score.drivers.items()}

    return S.ValuationDetail(
        meta=_meta(as_of), ticker=ticker,
        name=inst.name if inst else None, group_key=inst.group_key if inst else None,
        valuation_score=score.valuation_score if score else None,
        growth_score=score.growth_score if score else None,
        quality_score=score.quality_score if score else None,
        revision_score=score.revision_score if score else None,
        trend_score=score.trend_score if score else None,
        composite_score=score.composite_score if score else None,
        valuation_verdict=score.valuation_verdict if score else None,
        horizon_verdict=score.horizon_verdict if score else None,
        bubble_flag=score.bubble_flag if score else False,
        confidence=score.confidence if score else None,
        unreliable=bool(score and (score.confidence or 0) < CONF_UNRELIABLE),
        drivers=drivers, metrics=metrics,
        latest_financials=[S.FinancialRow(period_end=f.period_end, period_type=f.period_type,
                                          revenue=f.revenue, net_income=f.net_income,
                                          eps_diluted=f.eps_diluted, operating_income=f.operating_income)
                           for f in fins],
        estimates=[S.EstimateRow(horizon=e.horizon, metric=e.metric, avg=e.avg, low=e.low,
                                 high=e.high, n_analysts=e.n_analysts, year_ago_value=e.year_ago_value)
                   for e in ests],
        earnings_history=[S.EarningsRow(period_end=e.period_end, eps_actual=e.eps_actual,
                                        eps_estimate=e.eps_estimate, surprise_pct=e.surprise_pct)
                          for e in earn],
    )
