"""Dark Pool testy — gating (Pro+), ingest tokenem, roundtrip."""
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
from tests._auth import auth_headers

TOKEN = {"X-Internal-Token": "test-token"}


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_gating_pro():
    async with _client() as c:
        assert (await c.get("/api/darkpool")).status_code == 401  # bez tokenu
        h_free = await auth_headers(c, "dp_free@example.com")
        assert (await c.get("/api/darkpool", headers=h_free)).status_code == 403  # free
        h_pro = await auth_headers(c, "dp_pro@example.com", plan="pro")
        assert (await c.get("/api/darkpool", headers=h_pro)).status_code == 200  # pro


@pytest.mark.asyncio
async def test_ingest_requires_token_and_roundtrip():
    async with _client() as c:
        assert (await c.post("/api/darkpool/ingest", json={"items": []})).status_code in (401, 403)
        payload = {"week": "2026-09-07", "count": 1, "items": [
            {"symbol": "SPY", "name": "SPDR S&P 500", "shares": 40000000, "trades": 357315,
             "notional": 30738501505, "avg_trade": 86026, "tier": "NMS Tier 1"}]}
        r = await c.post("/api/darkpool/ingest", json=payload, headers=TOKEN)
        assert r.status_code == 200 and r.json()["items"] == 1
        h_pro = await auth_headers(c, "dp2@example.com", plan="pro")
        d = (await c.get("/api/darkpool", headers=h_pro)).json()
        assert d["week"] == "2026-09-07" and d["items"][0]["symbol"] == "SPY"


@pytest.mark.asyncio
async def test_ingest_rejects_bad_payload():
    async with _client() as c:
        r = await c.post("/api/darkpool/ingest", json={"nope": 1}, headers=TOKEN)
        assert r.json()["status"] == "error"
