"""Market statistiky z DB: publish jen s tokenem, ORB veřejné, Stats jen Trader+, žádná CDN cache placených dat."""
import os
import pytest

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["ANTHROPIC_API_KEY"] = "test-key"
os.environ["INTERNAL_API_TOKEN"] = "test-token"

from httpx import AsyncClient, ASGITransport
from app.main import app, _cache_header
from app.db.base import Base
from app.db.engine import engine
from tests._auth import auth_headers

TOKEN = {"X-Internal-Token": "test-token"}
BLOB = {"meta": {"instrument": "EURUSD", "unit": "pipů", "to": "2026-10-20"}, "session_sizes": {"ny": {"avg": 37.4}}}


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
async def test_publish_requires_token_and_validates():
    async with _client() as c:
        assert (await c.put("/api/marketstats/orb/eurusd", json=BLOB)).status_code == 401
        assert (await c.put("/api/marketstats/orb/eurusd", json={"x": 1}, headers=TOKEN)).status_code == 422
        assert (await c.put("/api/marketstats/bad/eurusd", json=BLOB, headers=TOKEN)).status_code == 404
        assert (await c.put("/api/marketstats/orb/..%2Fx", json=BLOB, headers=TOKEN)).status_code == 404
        r = await c.put("/api/marketstats/orb/eurusd", json=BLOB, headers=TOKEN)
        assert r.status_code == 200 and r.json()["name"] == "orb:eurusd" and r.json()["to"] == "2026-10-20"


@pytest.mark.asyncio
async def test_orb_public_roundtrip_and_update():
    async with _client() as c:
        assert (await c.get("/api/marketstats/orb/eurusd")).status_code == 404
        await c.put("/api/marketstats/orb/eurusd", json=BLOB, headers=TOKEN)
        assert (await c.get("/api/marketstats/orb/eurusd")).json() == BLOB
        new = {**BLOB, "meta": {**BLOB["meta"], "to": "2026-11-01"}}
        await c.put("/api/marketstats/orb/eurusd", json=new, headers=TOKEN)
        assert (await c.get("/api/marketstats/orb/eurusd")).json()["meta"]["to"] == "2026-11-01"


@pytest.mark.asyncio
async def test_stats_gated_by_plan():
    async with _client() as c:
        await c.put("/api/marketstats/stats/eurusd", json=BLOB, headers=TOKEN)
        assert (await c.get("/api/marketstats/stats/eurusd")).status_code == 401
        free = await auth_headers(c, "free@x.cz")
        assert (await c.get("/api/marketstats/stats/eurusd", headers=free)).status_code == 403
        trader = await auth_headers(c, "tr@x.cz", plan="trader")
        r = await c.get("/api/marketstats/stats/eurusd", headers=trader)
        assert r.status_code == 200 and r.json() == BLOB


def test_cdn_cache_only_for_orb():
    assert _cache_header("/api/marketstats/orb/nq")
    assert _cache_header("/api/marketstats/stats/nq") is None
