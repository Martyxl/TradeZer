"""Testy gamma snapshot endpointů (GET celý/per-ticker + POST ingest s tokenem)."""
import os
import pytest

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["ANTHROPIC_API_KEY"] = "test-key"
os.environ["INTERNAL_API_TOKEN"] = "test-token"

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.base import Base
from app.db.engine import engine


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


_PAYLOAD = {
    "generated": "2026-09-19T10:00:00+00:00",
    "instruments": {
        "NQ": {"underlying": "QQQ", "spot": 480.0, "net_gex": 1.2e9,
               "regime": "positive", "flip": 472.5, "call_wall": 500, "put_wall": 460,
               "profile": [{"strike": 480, "gex": 3.3e8}], "contracts": 1200},
    },
}


@pytest.mark.asyncio
async def test_get_empty():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/gamma")
    assert resp.status_code == 200
    assert resp.json()["instruments"] == {}


@pytest.mark.asyncio
async def test_ingest_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/gamma/ingest", json=_PAYLOAD)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_roundtrip_and_per_ticker():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ing = await client.post("/api/gamma/ingest", json=_PAYLOAD,
                                headers={"X-Internal-Token": "test-token"})
        assert ing.status_code == 200
        assert ing.json()["instruments"] == 1

        full = await client.get("/api/gamma")
        assert full.json()["instruments"]["NQ"]["regime"] == "positive"

        one = await client.get("/api/gamma?ticker=nq")
        body = one.json()
    assert body["ticker"] == "NQ"
    assert body["instrument"]["call_wall"] == 500
    # neznámý ticker → instrument None, ne chyba
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        miss = await client.get("/api/gamma?ticker=ZZZ")
    assert miss.json()["instrument"] is None


@pytest.mark.asyncio
async def test_ingest_rejects_missing_instruments():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/gamma/ingest", json={"foo": 1},
                                 headers={"X-Internal-Token": "test-token"})
    assert resp.json()["status"] == "error"
