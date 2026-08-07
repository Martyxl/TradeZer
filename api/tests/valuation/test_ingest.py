"""P1 offline testy — ingest přes FixtureProvider (nikdy nesíťuje)."""
import pytest
from sqlalchemy import func, select

from app.valuation.models import (
    ValInstrument, ValRawSnapshot, ValFinancials, ValEstimate,
    ValEstimateTrend, ValEarningsHistory, ValPriceDaily,
)
from app.valuation.providers.fixture_provider import FixtureProvider
from app.valuation import ingest as ingest_mod


@pytest.fixture(autouse=True)
def _use_fixture_provider(monkeypatch):
    monkeypatch.setattr(ingest_mod, "get_provider", lambda name=None: FixtureProvider())


async def _seed_aapl(session):
    session.add(ValInstrument(ticker="AAPL", in_display_universe=True, in_peer_universe=True))
    await session.commit()


async def _count(session, model) -> int:
    return await session.scalar(select(func.count()).select_from(model))


@pytest.mark.asyncio
async def test_ingest_populates_tables(db_session):
    await _seed_aapl(db_session)
    stats = await ingest_mod.ingest_all(db_session, tickers=["AAPL"])

    assert stats["fetched"] == 1 and stats["failed"] == 0
    assert await _count(db_session, ValFinancials) == 4
    assert await _count(db_session, ValEstimate) == 3
    assert await _count(db_session, ValEstimateTrend) == 1
    assert await _count(db_session, ValEarningsHistory) == 4
    assert await _count(db_session, ValPriceDaily) == 2
    # 6 endpointů = 6 raw snapshotů
    assert await _count(db_session, ValRawSnapshot) == 6

    # Profil se propsal do instrumentu + skupina z GICS (IT → tech)
    inst = await db_session.scalar(select(ValInstrument).where(ValInstrument.ticker == "AAPL"))
    assert inst.name == "Apple Inc."
    assert inst.gics_sector == "Information Technology"
    assert inst.group_key == "tech"


@pytest.mark.asyncio
async def test_ingest_idempotent(db_session):
    await _seed_aapl(db_session)
    await ingest_mod.ingest_all(db_session, tickers=["AAPL"])
    fin1 = await _count(db_session, ValFinancials)
    raw1 = await _count(db_session, ValRawSnapshot)

    # Druhý běh za stejný den = cache hit, žádné duplicity
    stats2 = await ingest_mod.ingest_all(db_session, tickers=["AAPL"])
    assert stats2["cache"] == 1
    assert await _count(db_session, ValFinancials) == fin1
    assert await _count(db_session, ValRawSnapshot) == raw1


@pytest.mark.asyncio
async def test_missing_ticker_does_not_crash(db_session):
    # Ticker bez fixture → prázdné sekce, žádná výjimka, žádné řádky
    stats = await ingest_mod.ingest_all(db_session, tickers=["NOPE"])
    assert stats["failed"] == 0
    assert await _count(db_session, ValFinancials) == 0
