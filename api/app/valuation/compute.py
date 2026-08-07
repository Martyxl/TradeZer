"""Orchestrace výpočtu metrik: čte z DB → metrics.py → peer.py → val_metrics_daily.

CLI: python -m app.valuation.compute
Čte jen z DB (žádné volání providerů). Peer z-score se počítá v rámci group_key
nad PEER_UNIVERSE.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime

import structlog
from sqlalchemy import select

from app.config import settings
from app.db.base import Base
from app.db.engine import engine
from app.db.session import session_context
from app.valuation import metrics as M
from app.valuation.peer import peer_zscores
from app.valuation.models import (
    ValInstrument, ValFinancials, ValEstimate, ValEstimateTrend,
    ValEarningsHistory, ValPriceDaily, ValMetricsDaily,
)

log = structlog.get_logger(__name__)


async def _load_ticker_inputs(session, ticker: str) -> dict:
    """Načte vše potřebné pro výpočet metrik jednoho tickeru."""
    # Kvartály (nejnovější revize per period_end), DESC
    fin = (await session.execute(
        select(ValFinancials).where(ValFinancials.ticker == ticker)
        .order_by(ValFinancials.period_end.desc(), ValFinancials.revision_no.desc())
    )).scalars().all()
    seen_q, seen_a, quarters, annual = set(), set(), [], []
    for f in fin:
        row = dict(
            period_end=f.period_end, report_date=f.report_date, revenue=f.revenue,
            gross_profit=f.gross_profit, operating_income=f.operating_income, ebitda=f.ebitda,
            net_income=f.net_income, eps_diluted=f.eps_diluted, shares_diluted=f.shares_diluted,
            cfo=f.cfo, capex=f.capex, total_debt=f.total_debt,
            cash_and_equivalents=f.cash_and_equivalents, total_equity=f.total_equity,
        )
        if f.period_type == "Q" and f.period_end not in seen_q:
            seen_q.add(f.period_end); quarters.append(row)
        elif f.period_type == "FY" and f.period_end not in seen_a:
            seen_a.add(f.period_end); annual.append(row)

    # Odhady: nejnovější as_of per (horizon, metric)
    est_rows = (await session.execute(
        select(ValEstimate).where(ValEstimate.ticker == ticker)
        .order_by(ValEstimate.as_of_date.desc())
    )).scalars().all()
    estimates: dict = {}
    for e in est_rows:
        key = (e.horizon, e.metric)
        if key not in estimates:
            estimates[key] = {"avg": e.avg, "low": e.low, "high": e.high, "n_analysts": e.n_analysts}

    # Trend: nejnovější as_of per horizon
    tr_rows = (await session.execute(
        select(ValEstimateTrend).where(ValEstimateTrend.ticker == ticker)
        .order_by(ValEstimateTrend.as_of_date.desc())
    )).scalars().all()
    trend: dict = {}
    for t in tr_rows:
        if t.horizon not in trend:
            trend[t.horizon] = {
                "current": t.current, "days_ago_90": t.days_ago_90,
                "up_last_30d": t.up_last_30d, "down_last_30d": t.down_last_30d,
            }

    # Surprises (nejnovější první)
    earn = (await session.execute(
        select(ValEarningsHistory).where(ValEarningsHistory.ticker == ticker)
        .order_by(ValEarningsHistory.period_end.desc())
    )).scalars().all()
    surprises = [e.surprise_pct for e in earn]

    # Ceny ASC (jen close potřeba)
    prices = (await session.execute(
        select(ValPriceDaily.date, ValPriceDaily.close).where(ValPriceDaily.ticker == ticker)
        .order_by(ValPriceDaily.date.asc())
    )).all()
    price_list = [{"date": d, "close": c} for d, c in prices]
    close = price_list[-1]["close"] if price_list else None

    fy_end_month = annual[0]["period_end"].month if annual else 12
    return dict(quarters=quarters, annual=annual, estimates=estimates, trend=trend,
                surprises=surprises, prices=price_list, close=close, fy_end_month=fy_end_month)


async def compute_all(session, as_of: date | None = None) -> dict:
    as_of = as_of or datetime.utcnow().date()
    version = settings.val_model_version

    instruments = (await session.execute(
        select(ValInstrument).where(ValInstrument.in_peer_universe == True)  # noqa: E712
    )).scalars().all()

    # 1) single-ticker metriky
    metric_by_ticker: dict[str, M.MetricSet] = {}
    group_of: dict[str, str | None] = {}
    for inst in instruments:
        try:
            inputs = await _load_ticker_inputs(session, inst.ticker)
            ms = M.compute_metrics(
                ticker=inst.ticker, as_of=as_of, close=inputs["close"],
                quarters=inputs["quarters"], annual=inputs["annual"],
                estimates=inputs["estimates"], trend=inputs["trend"],
                surprises=inputs["surprises"], prices=inputs["prices"],
                fy_end_month=inputs["fy_end_month"],
            )
            metric_by_ticker[inst.ticker] = ms
            group_of[inst.ticker] = inst.group_key
        except Exception as e:  # noqa: BLE001
            log.error("Metrics compute failed", ticker=inst.ticker, error=str(e))

    # 2) peer z-score v rámci skupin
    groups: dict[str, list[str]] = {}
    for t, g in group_of.items():
        groups.setdefault(g or "_none", []).append(t)
    for g, tickers in groups.items():
        pe = {t: metric_by_ticker[t].pe_fwd for t in tickers}
        ev = {t: metric_by_ticker[t].ev_ebitda for t in tickers}
        z_pe = peer_zscores(pe)
        z_ev = peer_zscores(ev)
        for t in tickers:
            metric_by_ticker[t].z_pe_fwd = z_pe[t]
            metric_by_ticker[t].z_ev_ebitda = z_ev[t]

    # 3) zápis val_metrics_daily (upsert)
    written = 0
    for t, ms in metric_by_ticker.items():
        existing = await session.scalar(select(ValMetricsDaily).where(
            ValMetricsDaily.ticker == t, ValMetricsDaily.as_of_date == as_of,
            ValMetricsDaily.model_version == version,
        ))
        if existing:
            existing.metrics = ms.to_dict()
        else:
            session.add(ValMetricsDaily(
                ticker=t, as_of_date=as_of, metrics=ms.to_dict(), model_version=version))
        written += 1
    await session.commit()

    stats = {"instruments": len(instruments), "computed": len(metric_by_ticker),
             "written": written, "model_version": version}
    log.info("Metrics compute complete", **stats)
    return stats


async def _main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_context() as session:
        stats = await compute_all(session)
    print(f"Metrics [{stats['model_version']}]: {stats['computed']}/{stats['instruments']} "
          f"spočítáno, {stats['written']} zapsáno")


if __name__ == "__main__":
    asyncio.run(_main())
