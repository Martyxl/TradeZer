"""Valuation Radar API. Konvence repa: /api/valuation, bez verzování.

Čte jen z DB (žádné volání providerů z request pathu). Každá response nese
meta (as_of_date, model_version, data_source, disclaimer).
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.routers.admin import _verify_token
from app.valuation import schemas as S
from app.valuation.models import (
    ValGroup, ValInstrument, ValScoreDaily, ValMetricsDaily,
    ValFinancials, ValEstimate, ValEarningsHistory, ValScoreRun,
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


# ---- static routes (před dynamickým /{ticker}) ------------------------------

@router.get("/groups", response_model=S.GroupsResponse)
async def groups(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(ValGroup).order_by(ValGroup.sort_order))).scalars().all()
    return S.GroupsResponse(
        meta=_meta(None),
        groups=[S.GroupOut(key=g.key, label_cs=g.label_cs, label_en=g.label_en,
                           color_hex=g.color_hex, sort_order=g.sort_order) for g in rows],
    )


@router.get("/overview", response_model=S.OverviewResponse)
async def overview(
    group: str | None = Query(default=None),
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
    session: AsyncSession = Depends(get_session),
):
    as_of = await _latest_score_date(session)
    if as_of is None:
        return S.OverviewResponse(meta=_meta(None), items=[])

    version = settings.val_model_version
    scores = (await session.execute(select(ValScoreDaily).where(
        ValScoreDaily.as_of_date == as_of, ValScoreDaily.model_version == version))).scalars().all()
    metrics = {m.ticker: m.metrics for m in (await session.execute(select(ValMetricsDaily).where(
        ValMetricsDaily.as_of_date == as_of, ValMetricsDaily.model_version == version))).scalars().all()}
    instruments = {i.ticker: i for i in (await session.execute(
        select(ValInstrument).where(ValInstrument.in_display_universe == True))).scalars().all()}  # noqa: E712

    items = []
    for s in scores:
        inst = instruments.get(s.ticker)
        if inst is None:  # jen display univerzum
            continue
        if group and inst.group_key != group:
            continue
        if (s.confidence or 0) < min_confidence:
            continue
        m = metrics.get(s.ticker, {})
        items.append(S.OverviewItem(
            ticker=s.ticker, name=inst.name, group_key=inst.group_key,
            pctile_pe_fwd=m.get("pctile_pe_fwd"), eps_growth_ntm=m.get("eps_growth_ntm"),
            market_cap=m.get("market_cap"), valuation_score=s.valuation_score,
            composite_score=s.composite_score, valuation_verdict=s.valuation_verdict,
            horizon_verdict=s.horizon_verdict, bubble_flag=s.bubble_flag, confidence=s.confidence,
        ))
    items.sort(key=lambda x: (x.composite_score or -1), reverse=True)
    return S.OverviewResponse(meta=_meta(as_of), items=items)


@router.post("/refresh", response_model=S.RefreshResponse, dependencies=[Depends(_verify_token)])
async def refresh(
    with_ingest: bool = Query(default=False, description="Zahrne i ingest (pomalé, jen mimo Vercel)"),
    tickers: str | None = Query(default=None, description="CSV omezení tickerů (jinak celé peer univerzum)"),
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
        stages["ingest"] = await ingest_all(session, tickers=tick_list)
    # Když je zadán ticker list, scope i compute/score (jinak by přepočet přes celé
    # univerzum přetáhl 60s Vercel limit).
    stages["compute"] = await compute_all(session, tickers=tick_list)
    score_stats = await score_all(session, tickers=tick_list)
    stages["score"] = score_stats
    return S.RefreshResponse(meta=_meta(await _latest_score_date(session)),
                             status="ok", run_id=score_stats.get("run_id"), stages=stages)


@router.post("/seed", dependencies=[Depends(_verify_token)])
async def seed(session: AsyncSession = Depends(get_session)):
    """Naplní val_groups + val_instruments (běžící DB se přes app.db.seed neplní)."""
    from app.db.seed_valuation import seed_valuation
    stats = await seed_valuation(session)
    return {"status": "ok", **stats}


@router.get("/runs/{run_id}", response_model=S.RunOut)
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


@router.get("/debug/fmpraw", dependencies=[Depends(_verify_token)])
async def debug_fmpraw(ticker: str = Query(default="AAPL")):
    """Syrové FMP odpovědi (status+tělo) na klíčové endpointy. Dočasná diagnostika."""
    import asyncio
    import httpx
    from app.config import settings
    from app.valuation.providers.fmp_provider import BASE

    def _probe():
        key = settings.fmp_api_key
        out = {}
        for label, path, params in (
            ("income", "income-statement", {"symbol": ticker, "period": "quarter", "limit": 1}),
            ("estimates", "analyst-estimates", {"symbol": ticker, "period": "annual", "limit": 1}),
            ("prices", "historical-price-eod/full", {"symbol": ticker, "from": "2026-07-01", "to": "2026-07-05"}),
        ):
            try:
                r = httpx.get(f"{BASE}/{path}", params={**params, "apikey": key}, timeout=20)
                out[label] = {"status": r.status_code, "body": r.text[:200]}
            except Exception as e:
                out[label] = {"err": str(e)[:150]}
        return out

    return await asyncio.to_thread(_probe)


@router.get("/backtest")
async def backtest(session: AsyncSession = Depends(get_session)):
    """Skóre vs. budoucí výnos (1M/3M). Roste s historií skóre."""
    from app.valuation.backtest import run_backtest
    result = await run_backtest(session)
    return {"meta": _meta(await _latest_score_date(session)).model_dump(), **result}


# ---- dynamické routes -------------------------------------------------------

@router.get("/{ticker}/summary")
async def ticker_summary(ticker: str, session: AsyncSession = Depends(get_session)):
    """LLM shrnutí nad spočítanými čísly (cache 24 h). Prázdné, když LLM nedostupné."""
    from app.valuation.summary import get_summary
    result = await get_summary(session, ticker)
    return {"meta": _meta(None).model_dump(), **result}


@router.get("/{ticker}/history", response_model=S.HistoryResponse)
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


@router.get("/{ticker}", response_model=S.ValuationDetail)
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
