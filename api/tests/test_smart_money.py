"""Testy smart-money snapshot endpointů (GET čtení + POST ingest s tokenem)."""
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
    "generated": "2026-09-19T10:00:00+00:00", "source": "sec_form4",
    "count": 1, "buys": 1, "sells": 0,
    "top_buys": [{"ticker": "SOFI", "issuer": "SoFi", "buys": 1, "sells": 0,
                  "buy_value": 250000, "sell_value": 0}],
    "insiders": [{"date": "2026-09-18", "person": "Jane Doe", "role": "director",
                  "ticker": "SOFI", "issuer": "SoFi", "tx": "buy",
                  "shares": 20000, "price": 12.5, "value": 250000}],
    "congress": [],
}


@pytest.mark.asyncio
async def test_get_empty():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/smart-money")
    assert resp.status_code == 200
    assert resp.json()["insiders"] == []


@pytest.mark.asyncio
async def test_ingest_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/smart-money/ingest", json=_PAYLOAD)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_roundtrip():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ing = await client.post("/api/smart-money/ingest", json=_PAYLOAD,
                                headers={"X-Internal-Token": "test-token"})
        assert ing.status_code == 200 and ing.json()["insiders"] == 1
        got = await client.get("/api/smart-money")
    body = got.json()
    assert body["insiders"][0]["ticker"] == "SOFI"
    assert body["top_buys"][0]["buy_value"] == 250000


@pytest.mark.asyncio
async def test_ingest_rejects_missing_insiders():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/smart-money/ingest", json={"x": 1},
                                 headers={"X-Internal-Token": "test-token"})
    assert resp.json()["status"] == "error"
