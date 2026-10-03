"""Testy investorského deníku — CRUD, výpočet portfolia (průměrná cena, realized),
živé ceny + FX přepočet do base měny, dedup importu."""
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


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


TOKEN = {"X-Internal-Token": "test-token"}


@pytest.mark.asyncio
async def test_crud_requires_auth():
    async with _client() as c:
        assert (await c.get("/api/investments")).status_code == 401
        assert (await c.post("/api/investments", json={})).status_code == 401


@pytest.mark.asyncio
async def test_portfolio_avg_cost_and_live_value():
    async with _client() as c:
        h = await auth_headers(c, "inv@example.com")
        # 10 AAPL @100 (+5 fee), 10 @120, prodej 5 @130
        await c.post("/api/investments", json={"tx_type": "buy", "symbol": "AAPL", "quantity": 10, "price": 100, "fee": 5, "currency": "USD", "executed_at": "2026-01-01"}, headers=h)
        await c.post("/api/investments", json={"tx_type": "buy", "symbol": "AAPL", "quantity": 10, "price": 120, "currency": "USD", "executed_at": "2026-02-01"}, headers=h)
        await c.post("/api/investments", json={"tx_type": "sell", "symbol": "AAPL", "quantity": 5, "price": 130, "currency": "USD", "executed_at": "2026-03-01"}, headers=h)
        # živé ceny + FX
        await c.post("/api/investments/quotes/ingest", json={"quotes": [
            {"symbol": "AAPL", "price": 150, "currency": "USD"},
            {"symbol": "USDCZK", "price": 23},
        ]}, headers=TOKEN)

        r = await c.get("/api/investments/portfolio?base=CZK", headers=h)
        assert r.status_code == 200, r.text
        d = r.json()
        hold = {x["symbol"]: x for x in d["holdings"]}["AAPL"]
        assert hold["quantity"] == 15
        assert abs(hold["avg_cost"] - 110.25) < 0.01          # (1005+1200)/20 avg, po prodeji drží
        assert abs(hold["invested"] - 1653.75) < 0.01
        assert abs(hold["value"] - 2250) < 0.01               # 15 × 150
        assert abs(hold["unrealized"] - 596.25) < 0.01
        # realized z prodeje: (130 - 110.25) × 5 = 98.75
        assert abs(d["realized_by_currency"]["USD"] - 98.75) < 0.01
        # base přepočet CZK: value 2250×23
        assert abs(d["base_totals"]["value"] - 2250 * 23) < 1
        assert d["base_totals"]["complete"] is True


@pytest.mark.asyncio
async def test_import_dedup():
    async with _client() as c:
        h = await auth_headers(c, "inv2@example.com")
        rows = [{"tx_type": "buy", "symbol": "MSFT", "quantity": 2, "price": 300, "currency": "USD", "executed_at": "2026-01-05"}]
        r1 = await c.post("/api/investments/import", json={"rows": rows, "broker": "xtb"}, headers=h)
        assert r1.json()["created"] == 1
        r2 = await c.post("/api/investments/import", json={"rows": rows, "broker": "xtb"}, headers=h)
        assert r2.json()["created"] == 0 and r2.json()["skipped"] == 1


@pytest.mark.asyncio
async def test_symbols_internal_only():
    async with _client() as c:
        h = await auth_headers(c, "inv3@example.com")
        await c.post("/api/investments", json={"tx_type": "buy", "symbol": "nvda", "quantity": 1, "price": 100, "currency": "USD"}, headers=h)
        assert (await c.get("/api/investments/symbols")).status_code in (401, 403)
        r = await c.get("/api/investments/symbols", headers=TOKEN)
        assert r.status_code == 200
        assert "NVDA" in r.json()["symbols"]
