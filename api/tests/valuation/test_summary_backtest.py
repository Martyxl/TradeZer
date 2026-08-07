"""P6 testy — LLM shrnutí (cache, mock) + backtest (synteticky)."""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.valuation.models import (
    ValInstrument, ValScoreDaily, ValMetricsDaily, ValPriceDaily, ValSummary,
)
from app.valuation import summary as summary_mod
from app.valuation.backtest import run_backtest

VER = "val-1.0.0"


async def _seed_score(session, ticker="AAPL", as_of=None, composite=60.0, verdict="FÉROVÁ"):
    as_of = as_of or date.today()
    session.add(ValInstrument(ticker=ticker, name="Apple", group_key="tech",
                              in_display_universe=True, in_peer_universe=True))
    session.add(ValMetricsDaily(ticker=ticker, as_of_date=as_of, model_version=VER,
                                metrics={"pe_fwd": 30, "pctile_pe_fwd": 55, "eps_growth_ntm": 12}))
    session.add(ValScoreDaily(ticker=ticker, as_of_date=as_of, model_version=VER,
                              valuation_score=58, composite_score=composite,
                              valuation_verdict=verdict, horizon_verdict="NEUTRÁLNÍ",
                              bubble_flag=False, confidence=0.8))
    await session.commit()


@pytest.mark.asyncio
async def test_summary_uses_llm_and_caches(db_session, monkeypatch):
    await _seed_score(db_session)
    calls = {"n": 0}

    def fake_llm(payload):
        calls["n"] += 1
        return "- Ferova valuace.\n- Rust EPS 12 %.\n- Bez doporuceni."

    monkeypatch.setattr(summary_mod, "_call_llm", fake_llm)

    r1 = await summary_mod.get_summary(db_session, "AAPL")
    assert r1["summary"].startswith("- ") and r1["cached"] is False
    assert calls["n"] == 1

    # druhé volání = stejná čísla → cache, LLM se nevolá znovu
    r2 = await summary_mod.get_summary(db_session, "AAPL")
    assert r2["cached"] is True
    assert calls["n"] == 1
    assert await db_session.scalar(select(ValSummary).where(ValSummary.ticker == "AAPL")) is not None


@pytest.mark.asyncio
async def test_summary_empty_when_llm_fails(db_session, monkeypatch):
    await _seed_score(db_session, ticker="COST")
    monkeypatch.setattr(summary_mod, "_call_llm", lambda payload: None)
    r = await summary_mod.get_summary(db_session, "COST")
    assert r["summary"] == "" and r["cached"] is False


@pytest.mark.asyncio
async def test_summary_no_score_returns_empty(db_session):
    r = await summary_mod.get_summary(db_session, "ZZZZ")
    assert r["summary"] == ""


@pytest.mark.asyncio
async def test_backtest_forward_returns(db_session):
    as_of = date(2026, 1, 5)
    await _seed_score(db_session, ticker="NQX", as_of=as_of, composite=75.0, verdict="LEVNÁ")
    # cena k datu skóre a +30/+90 dní (růst)
    for d, c in [(as_of, 100.0), (as_of + timedelta(days=30), 110.0), (as_of + timedelta(days=90), 130.0)]:
        db_session.add(ValPriceDaily(ticker="NQX", date=d, close=c))
    await db_session.commit()

    bt = await run_backtest(db_session)
    assert bt["scores_evaluated"] == 1
    m1 = bt["horizons"]["1m"]["by_composite"]["70-100"]
    assert m1["n"] == 1 and abs(m1["avg_return_pct"] - 10.0) < 0.01
    m3 = bt["horizons"]["3m"]["by_verdict"]["LEVNÁ"]
    assert abs(m3["avg_return_pct"] - 30.0) < 0.01


@pytest.mark.asyncio
async def test_backtest_empty_ok(db_session):
    bt = await run_backtest(db_session)
    assert bt["scores_evaluated"] == 0
