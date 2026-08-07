"""Orchestrace skórování: val_metrics_daily → scoring engine → val_scores_daily.

CLI: python -m app.valuation.score
Předpokládá, že P2 (compute) už naplnil val_metrics_daily pro daný den.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime

import structlog
from sqlalchemy import func, select

from app.config import settings
from app.db.base import Base
from app.db.engine import engine
from app.db.session import session_context
from app.valuation.models import (
    ValMetricsDaily, ValScoreDaily, ValScoreRun, ValEstimate, ValPriceDaily,
)
from app.valuation.scoring import score_metrics

log = structlog.get_logger(__name__)


async def _n_analysts(session, ticker: str) -> int | None:
    row = (await session.execute(
        select(ValEstimate.n_analysts).where(
            ValEstimate.ticker == ticker, ValEstimate.horizon == "current_y",
            ValEstimate.metric == "eps",
        ).order_by(ValEstimate.as_of_date.desc()).limit(1)
    )).first()
    return row[0] if row else None


async def _years_history(session, ticker: str) -> float | None:
    lo = await session.scalar(select(func.min(ValPriceDaily.date)).where(ValPriceDaily.ticker == ticker))
    hi = await session.scalar(select(func.max(ValPriceDaily.date)).where(ValPriceDaily.ticker == ticker))
    if not lo or not hi:
        return None
    return (hi - lo).days / 365.25


async def score_all(session, as_of: date | None = None) -> dict:
    as_of = as_of or datetime.utcnow().date()
    version = settings.val_model_version
    run = ValScoreRun(model_version=version)
    session.add(run)
    await session.flush()

    rows = (await session.execute(
        select(ValMetricsDaily).where(
            ValMetricsDaily.as_of_date == as_of, ValMetricsDaily.model_version == version)
    )).scalars().all()

    ok = failed = 0
    for mrow in rows:
        try:
            n_an = await _n_analysts(session, mrow.ticker)
            yrs = await _years_history(session, mrow.ticker)
            result = score_metrics(mrow.metrics, n_analysts=n_an, years_history=yrs)

            existing = await session.scalar(select(ValScoreDaily).where(
                ValScoreDaily.ticker == mrow.ticker, ValScoreDaily.as_of_date == as_of,
                ValScoreDaily.model_version == version))
            target = existing or ValScoreDaily(ticker=mrow.ticker, as_of_date=as_of, model_version=version)
            target.valuation_score = result.valuation_score
            target.growth_score = result.growth_score
            target.quality_score = result.quality_score
            target.revision_score = result.revision_score
            target.trend_score = result.trend_score
            target.composite_score = result.composite_score
            target.valuation_verdict = result.valuation_verdict
            target.horizon_verdict = result.horizon_verdict
            target.bubble_flag = result.bubble_flag
            target.confidence = result.confidence
            target.drivers = result.drivers
            if not existing:
                session.add(target)
            ok += 1
        except Exception as e:  # noqa: BLE001
            failed += 1
            log.error("Score failed", ticker=mrow.ticker, error=str(e))

    run.finished_at = datetime.utcnow()
    run.tickers_ok = ok
    run.tickers_failed = failed
    await session.commit()

    stats = {"run_id": run.id, "scored": ok, "failed": failed, "model_version": version}
    log.info("Scoring complete", **stats)
    return stats


async def _main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_context() as session:
        stats = await score_all(session)
    print(f"Scoring [{stats['model_version']}] run #{stats['run_id']}: "
          f"{stats['scored']} skóre, {stats['failed']} chyb")


if __name__ == "__main__":
    asyncio.run(_main())
