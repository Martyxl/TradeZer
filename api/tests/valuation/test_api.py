"""P4 testy — Valuation API endpointy (offline, přes FixtureProvider)."""
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.db import get_session
from app.valuation.models import ValInstrument
from app.valuation.providers.fixture_provider import FixtureProvider
from app.valuation import ingest as ingest_mod
from app.valuation import compute as compute_mod
from app.valuation import score as score_mod
from app.db.seed_valuation import seed_valuation


@pytest.fixture(autouse=True)
def _fixture_provider(monkeypatch):
    monkeypatch.setattr(ingest_mod, "get_provider", lambda name=None: FixtureProvider())


@pytest.fixture
async def client(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def _prepare(session):
    await seed_valuation(session)  # groups + universe
    # zúžíme na 2 display tickery s fixtures
    for t in ("AAPL", "COST"):
        inst = await session.get(ValInstrument, t)
        if inst:
            inst.in_display_universe = True
    await session.commit()
    await ingest_mod.ingest_all(session, tickers=["AAPL", "COST"])
    await compute_mod.compute_all(session)
    await score_mod.score_all(session)


@pytest.mark.asyncio
async def test_groups_endpoint(client, db_session):
    await _prepare(db_session)
    r = await client.get("/api/valuation/groups")
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["disclaimer"]
    assert any(g["key"] == "tech" for g in body["groups"])


@pytest.mark.asyncio
async def test_overview_and_filters(client, db_session):
    await _prepare(db_session)
    r = await client.get("/api/valuation/overview")
    assert r.status_code == 200
    items = r.json()["items"]
    tickers = {i["ticker"] for i in items}
    assert {"AAPL", "COST"} & tickers
    for it in items:
        assert "pctile_pe_fwd" in it and "composite_score" in it

    # min_confidence filtr vrací podmnožinu
    r2 = await client.get("/api/valuation/overview?min_confidence=0.99")
    assert len(r2.json()["items"]) <= len(items)


@pytest.mark.asyncio
async def test_detail_endpoint(client, db_session):
    await _prepare(db_session)
    r = await client.get("/api/valuation/AAPL")
    assert r.status_code == 200
    d = r.json()
    assert d["ticker"] == "AAPL"
    assert d["meta"]["disclaimer"]
    assert "drivers" in d and "metrics" in d
    assert len(d["latest_financials"]) > 0


@pytest.mark.asyncio
async def test_unknown_ticker_404(client, db_session):
    await _prepare(db_session)
    r = await client.get("/api/valuation/ZZZZ")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_refresh_requires_token(client, db_session):
    await _prepare(db_session)
    # bez tokenu → 401
    r = await client.post("/api/valuation/refresh")
    assert r.status_code == 401
    # s tokenem → ok, vrací run_id
    r2 = await client.post("/api/valuation/refresh", headers={"X-Internal-Token": "test-token"})
    assert r2.status_code == 200
    assert r2.json()["run_id"] is not None
