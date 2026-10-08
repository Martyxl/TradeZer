"""Testy AI fondu — veřejné GET, ingest tokenem, signals token-only."""
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
async def test_empty_public():
    async with _client() as c:
        r = await c.get("/api/fund")
    assert r.status_code == 200 and r.json()["state"] is None


@pytest.mark.asyncio
async def test_ingest_and_read():
    payload = {
        "state": {"start_capital": 1000000, "cash": 920000, "equity": 1010000, "base": "CZK",
                  "as_of": "2026-10-05T12:00:00", "note": "Dnes nakoupil AAPL."},
        "positions": [{"symbol": "AAPL", "name": "Apple", "quantity": 20, "avg_cost": 330,
                       "currency": "USD", "value_czk": 90000, "weight_pct": 8.9, "conviction": 55}],
        "trades": [{"ts": "2026-10-05T12:00:00", "action": "buy", "symbol": "AAPL", "name": "Apple",
                    "quantity": 20, "price": 330, "currency": "USD", "value_czk": 90000,
                    "conviction": 55, "reason": "valuace férová, insideři nakupují"}],
        "snapshots": [{"date": "2026-10-05", "equity": 1010000, "cash": 920000, "invested": 90000}],
    }
    async with _client() as c:
        assert (await c.post("/api/fund/ingest", json=payload)).status_code in (401, 403)  # bez tokenu
        r = await c.post("/api/fund/ingest", json=payload, headers=TOKEN)
        assert r.status_code == 200 and r.json()["positions"] == 1
        d = (await c.get("/api/fund")).json()
        assert d["state"]["pnl"] == 10000 and d["state"]["cash"] == 920000
        assert d["positions"][0]["symbol"] == "AAPL"
        assert "insideři" in d["trades"][0]["reason"]
        assert len(d["snapshots"]) == 1


@pytest.mark.asyncio
async def test_hourly_mark_without_trades_keeps_trades():
    """Hodinové přecenění posílá `trades: null` → obchody se nepřepisují (šetří Neon/Vercel)."""
    base = {"state": {"start_capital": 1000000, "cash": 920000, "equity": 1010000, "base": "CZK",
                      "as_of": "2026-10-05T12:00:00", "note": "x"},
            "positions": [], "snapshots": []}
    trade = {"ts": "2026-10-05T12:00:00", "action": "buy", "symbol": "AAPL", "quantity": 1, "price": 1,
             "currency": "USD", "reason": "r"}
    async with _client() as c:
        await c.post("/api/fund/ingest", json={**base, "trades": [trade]}, headers=TOKEN)
        r = await c.post("/api/fund/ingest", json={**base, "trades": None,
                                                   "state": {**base["state"], "equity": 1020000}}, headers=TOKEN)
        assert r.status_code == 200
        d = (await c.get("/api/fund")).json()
        assert len(d["trades"]) == 1 and d["state"]["equity"] == 1020000   # obchody zůstaly, equity se aktualizovalo
        # prázdný seznam = skutečné vymazání (Spark je zdroj pravdy)
        await c.post("/api/fund/ingest", json={**base, "trades": []}, headers=TOKEN)
        assert (await c.get("/api/fund")).json()["trades"] == []


@pytest.mark.asyncio
async def test_signals_token_only():
    async with _client() as c:
        assert (await c.get("/api/fund/signals")).status_code in (401, 403)
        r = await c.get("/api/fund/signals", headers=TOKEN)
        assert r.status_code == 200 and "valuation" in r.json()
