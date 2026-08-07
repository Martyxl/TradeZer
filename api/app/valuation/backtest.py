"""Jednoduchý backtest: koreluje skóre s budoucím výnosem (1M/3M).

Point-in-time: pro každé skóre k datu D vezme cenu k D a cenu k D+~30/90 dní.
Roste s tím, jak se hromadí historie skóre. Bez historie vrací prázdno.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.valuation.models import ValScoreDaily, ValPriceDaily


def _bucket(score: float | None) -> str | None:
    if score is None:
        return None
    if score >= 70:
        return "70-100"
    if score >= 55:
        return "55-70"
    if score >= 40:
        return "40-55"
    return "0-40"


async def _price_near(session, ticker: str, target: date, window: int = 6) -> float | None:
    row = (await session.execute(
        select(ValPriceDaily.close).where(
            ValPriceDaily.ticker == ticker,
            ValPriceDaily.date >= target - timedelta(days=window),
            ValPriceDaily.date <= target + timedelta(days=window),
            ValPriceDaily.close.is_not(None))
        .order_by(ValPriceDaily.date.asc()).limit(1))).first()
    return row[0] if row else None


async def run_backtest(session: AsyncSession) -> dict:
    version = settings.val_model_version
    scores = (await session.execute(select(ValScoreDaily).where(
        ValScoreDaily.model_version == version).order_by(ValScoreDaily.as_of_date.asc()))).scalars().all()

    horizons = {"1m": 30, "3m": 90}
    agg: dict = {h: {"by_verdict": {}, "by_composite": {}} for h in horizons}
    n_used = 0

    for s in scores:
        p0 = await _price_near(session, s.ticker, s.as_of_date)
        if not p0:
            continue
        used_any = False
        for h, days in horizons.items():
            pf = await _price_near(session, s.ticker, s.as_of_date + timedelta(days=days))
            if not pf:
                continue
            ret = (pf - p0) / p0 * 100
            used_any = True
            for key, bucket in (("by_verdict", s.valuation_verdict),
                                ("by_composite", _bucket(s.composite_score))):
                if bucket is None:
                    continue
                d = agg[h][key].setdefault(bucket, {"n": 0, "sum": 0.0})
                d["n"] += 1
                d["sum"] += ret
        if used_any:
            n_used += 1

    # průměry
    for h in horizons:
        for key in ("by_verdict", "by_composite"):
            for bucket, d in agg[h][key].items():
                d["avg_return_pct"] = round(d["sum"] / d["n"], 2) if d["n"] else None
                del d["sum"]

    return {"model_version": version, "scores_evaluated": n_used, "horizons": agg}
