"""Testy discovery snapshot endpointů (GET čtení + POST ingest s tokenem)."""
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


@pytest.mark.asyncio
async def test_get_empty_returns_envelope():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/discovery")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["scanned"] == 0


@pytest.mark.asyncio
async def test_ingest_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/discovery/ingest", json={"items": []})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_ingest_then_get_roundtrip():
    payload = {
        "generated": "2026-09-19T10:00:00+00:00",
        "universe_size": 2,
        "scanned": 1,
        "catalysts": True,
        "items": [{"ticker": "SOFI", "price": 12.3, "score": 71.2,
                   "market_cap": 12_000_000_000, "days_to_earnings": 3,
                   "earnings_date": "2026-09-22", "last_surprise_pct": 5.4}],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ing = await client.post("/api/discovery/ingest", json=payload,
                                headers={"X-Internal-Token": "test-token"})
        assert ing.status_code == 200
        assert ing.json()["items"] == 1

        got = await client.get("/api/discovery")
    assert got.status_code == 200
    body = got.json()
    assert body["items"][0]["ticker"] == "SOFI"
    assert body["items"][0]["days_to_earnings"] == 3
    assert body["catalysts"] is True


@pytest.mark.asyncio
async def test_ingest_rejects_missing_items():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/discovery/ingest", json={"foo": "bar"},
                                 headers={"X-Internal-Token": "test-token"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"
