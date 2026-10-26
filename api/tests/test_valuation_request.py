"""Testy: přidání akcie na přání (auth) + filtr overview na portfolio uživatele."""
import os
from datetime import date

import pytest

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["ANTHROPIC_API_KEY"] = "test-key"
os.environ["INTERNAL_API_TOKEN"] = "test-token"

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.config import settings
from app.db.base import Base
from app.db.engine import engine
from app.db.session import session_context
from app.valuation.models import ValInstrument, ValScoreDaily
from app.models import InvestmentTx, User
from tests._auth import auth_headers


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _seed_scored(tickers):
    mv = settings.val_model_version
    async with session_context() as s:
        for t in tickers:
            s.add(ValInstrument(ticker=t, name=t, group_key=None, in_display_universe=True, active=True))
            s.add(ValScoreDaily(ticker=t, as_of_date=date.today(), composite_score=50.0,
                                valuation_score=50.0, confidence=1.0, model_version=mv))
        await s.commit()


@pytest.mark.asyncio
async def test_request_requires_auth():
    async with _client() as c:
        r = await c.post("/api/valuation/request", json={"query": "AAPL"})
    assert r.status_code == 401  # bez tokenu (žádné síťové volání)


@pytest.mark.asyncio
async def test_overview_portfolio_filter():
    await _seed_scored(["AAPL", "MSFT"])
    async with _client() as c:
        h = await auth_headers(c, "val@example.com", plan="trader")
        # uživatel drží jen AAPL
        uid = (await c.get("/api/auth/me", headers=h)).json()["user"]["id"]
        async with session_context() as s:
            s.add(InvestmentTx(user_id=uid, tx_type="buy", symbol="AAPL", quantity=5, price=100, currency="USD"))
            await s.commit()

        allv = (await c.get("/api/valuation/overview", headers=h)).json()
        assert {i["ticker"] for i in allv["items"]} == {"AAPL", "MSFT"}

        mine = (await c.get("/api/valuation/overview?portfolio=true", headers=h)).json()
        assert {i["ticker"] for i in mine["items"]} == {"AAPL"}


@pytest.mark.asyncio
async def test_overview_portfolio_matches_suffix():
    """Držený OGN.US (broker suffix) se napáruje na valuation OGN."""
    await _seed_scored(["OGN"])
    async with _client() as c:
        h = await auth_headers(c, "val2@example.com", plan="trader")
        uid = (await c.get("/api/auth/me", headers=h)).json()["user"]["id"]
        async with session_context() as s:
            s.add(InvestmentTx(user_id=uid, tx_type="buy", symbol="OGN.US", quantity=3, price=14, currency="USD"))
            await s.commit()
        mine = (await c.get("/api/valuation/overview?portfolio=true", headers=h)).json()
        assert {i["ticker"] for i in mine["items"]} == {"OGN"}


def _no_network(monkeypatch, taxonomies=None, calls=None):
    """Bez sítě: resolve tickeru, ingest/compute/score a SEC taxonomie nahradit stuby."""
    import app.routers.valuation as V
    monkeypatch.setattr(V, "_resolve_ticker", lambda q: (q.upper(), f"{q.upper()} Inc."))

    async def ingest_all(*a, **k):
        if calls is not None:
            calls.append("ingest")
        return {}

    async def noop(*a, **k):
        return {}
    monkeypatch.setattr("app.valuation.ingest.ingest_all", ingest_all)
    monkeypatch.setattr("app.valuation.compute.compute_all", noop)
    monkeypatch.setattr("app.valuation.score.score_all", noop)
    monkeypatch.setattr("app.valuation.providers.sec_provider.SECEdgarProvider.taxonomies",
                        lambda self, t: taxonomies)


@pytest.mark.asyncio
async def test_existing_firm_is_shown_not_recomputed_and_interest_counted_once_per_user(monkeypatch):
    await _seed_scored(["SOFI"])
    calls = []
    _no_network(monkeypatch, calls=calls)
    async with _client() as c:
        a = await auth_headers(c, "a@x.cz", plan="trader")
        b = await auth_headers(c, "b@x.cz", plan="trader")
        r1 = (await c.post("/api/valuation/request", json={"query": "sofi"}, headers=a)).json()
        r2 = (await c.post("/api/valuation/request", json={"query": "sofi"}, headers=a)).json()   # stejný uživatel znovu
        r3 = (await c.post("/api/valuation/request", json={"query": "sofi"}, headers=b)).json()
    assert r1["status"] == r2["status"] == r3["status"] == "exists" and r1["computed"] is True
    assert (r1["request_count"], r2["request_count"], r3["request_count"]) == (1, 1, 2)
    assert calls == []                                    # žádný duplicitní výpočet


@pytest.mark.asyncio
async def test_foreign_ifrs_issuer_is_reported_not_displayed(monkeypatch):
    calls = []
    _no_network(monkeypatch, taxonomies={"ifrs-full", "dei"}, calls=calls)
    async with _client() as c:
        a = await auth_headers(c, "a@x.cz", plan="trader")
        r = (await c.post("/api/valuation/request", json={"query": "nu"}, headers=a)).json()
        assert r["status"] == "unsupported" and "IFRS" in r["message"]
        r2 = (await c.post("/api/valuation/request", json={"query": "nu"}, headers=a)).json()
        assert r2["status"] == "unsupported"
    assert calls == ["ingest"]                            # podruhé už se nic nestahuje
    async with session_context() as s:
        inst = await s.get(ValInstrument, "NU")
        assert inst.coverage_note == "foreign_ifrs" and inst.in_display_universe is False and inst.request_count == 1
