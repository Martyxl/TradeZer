"""P2 integrace — ingest (fixture) → compute → val_metrics_daily."""
import pytest
from sqlalchemy import select

from app.valuation.models import ValInstrument, ValMetricsDaily
from app.valuation.providers.fixture_provider import FixtureProvider
from app.valuation import ingest as ingest_mod
from app.valuation import compute as compute_mod


@pytest.fixture(autouse=True)
def _fixture_provider(monkeypatch):
    monkeypatch.setattr(ingest_mod, "get_provider", lambda name=None: FixtureProvider())


@pytest.mark.asyncio
async def test_compute_writes_metrics(db_session):
    db_session.add(ValInstrument(ticker="AAPL", in_display_universe=True, in_peer_universe=True))
    await db_session.commit()
    await ingest_mod.ingest_all(db_session, tickers=["AAPL"])

    stats = await compute_mod.compute_all(db_session)
    assert stats["computed"] == 1

    row = await db_session.scalar(select(ValMetricsDaily).where(ValMetricsDaily.ticker == "AAPL"))
    assert row is not None
    m = row.metrics
    # TTM EPS = 1.55+2.10+1.48+1.35 = 6.48; close 214 → pe_ttm ~33
    assert m["pe_ttm"] is not None and 30 < m["pe_ttm"] < 36
    assert m["market_cap"] is not None
    assert m["eps_growth_ntm"] is not None      # z konsenzu
    assert m["avg_surprise_4q"] is not None      # ze 4 earnings
    # peer z-score None (jen 1 firma ve skupině < 5)
    assert m["z_pe_fwd"] is None
