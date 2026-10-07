"""Režim trhu: prázdný stav, auth na ingest, validace, roundtrip."""
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
async def test_empty_then_roundtrip():
    async with _client() as c:
        assert (await c.get("/api/regime")).json()["state"] is None
        body = {"state": "tension", "label": "Napětí", "reasons": ["VIX 24"],
                "indicators": {"vix": 24.1}, "geo": {"severity": 2}}
        assert (await c.post("/api/regime/ingest", json=body)).status_code in (401, 403)
        r = await c.post("/api/regime/ingest", json=body, headers=TOKEN)
        assert r.json() == {"status": "ok", "state": "tension"}
        got = (await c.get("/api/regime")).json()
        assert got["state"] == "tension" and got["indicators"]["vix"] == 24.1 and got["as_of"]
        # přepis (jediný řádek)
        await c.post("/api/regime/ingest", json={**body, "state": "calm"}, headers=TOKEN)
        assert (await c.get("/api/regime")).json()["state"] == "calm"


@pytest.mark.asyncio
async def test_rejects_unknown_state():
    async with _client() as c:
        r = await c.post("/api/regime/ingest", json={"state": "foo"}, headers=TOKEN)
        assert r.json()["status"] == "error"
        assert (await c.get("/api/regime")).json()["state"] is None
