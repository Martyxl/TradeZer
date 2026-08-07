"""P3 golden pipeline — ingest(fixture) → compute → score, offline snapshot."""
import pytest
from sqlalchemy import select

from app.valuation.models import ValInstrument, ValScoreDaily
from app.valuation.providers.fixture_provider import FixtureProvider
from app.valuation import ingest as ingest_mod
from app.valuation import compute as compute_mod
from app.valuation import score as score_mod


@pytest.fixture(autouse=True)
def _fixture_provider(monkeypatch):
    monkeypatch.setattr(ingest_mod, "get_provider", lambda name=None: FixtureProvider())


async def _pipeline(session, tickers):
    for t in tickers:
        session.add(ValInstrument(ticker=t, in_display_universe=True, in_peer_universe=True))
    await session.commit()
    await ingest_mod.ingest_all(session, tickers=tickers)
    await compute_mod.compute_all(session)
    return await score_mod.score_all(session)


@pytest.mark.asyncio
async def test_full_pipeline_scores(db_session):
    stats = await _pipeline(db_session, ["AAPL", "COST", "MISS"])
    assert stats["scored"] == 3 and stats["failed"] == 0

    scores = {s.ticker: s for s in (await db_session.execute(select(ValScoreDaily))).scalars().all()}
    assert set(scores) == {"AAPL", "COST", "MISS"}

    # Kompletní data → composite i confidence vyplněné
    aapl = scores["AAPL"]
    assert aapl.composite_score is not None
    assert 0 <= aapl.composite_score <= 100
    assert aapl.valuation_verdict in ("LEVNÁ", "FÉROVÁ", "NAPJATÁ", "PŘEPÁLENÁ")
    assert aapl.confidence is not None and aapl.confidence > 0
    assert aapl.drivers and "positive" in aapl.drivers

    # Chudá data → nízká confidence, ale žádná výjimka a řádek existuje
    miss = scores["MISS"]
    assert miss.confidence is not None and miss.confidence < 0.5


@pytest.mark.asyncio
async def test_audit_run_recorded(db_session):
    from app.valuation.models import ValScoreRun
    stats = await _pipeline(db_session, ["COST"])
    run = await db_session.scalar(select(ValScoreRun).where(ValScoreRun.id == stats["run_id"]))
    assert run.finished_at is not None and run.tickers_ok == 1
