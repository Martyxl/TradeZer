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


def test_signal_rules():
    from app.routers.investments import _signal
    # velký zisk + velká váha + blízko 52T maxima → red + návrh trim
    red = _signal({"unrealized_pct": 80, "price": 100, "high_52w": 102, "low_52w": 50}, weight=20, raw_qty=10)
    assert red["color"] == "red" and red["trim_qty"] is not None
    # blízko 52T minima, malá váha → green + zóna dokupu
    green = _signal({"unrealized_pct": -5, "price": 52, "high_52w": 150, "low_52w": 50}, weight=3, raw_qty=10)
    assert green["color"] == "green" and green["add_zone"] is not None
    # bez ceny (žádný quote) → amber, nic nepadá
    amber = _signal({"unrealized_pct": None, "price": None, "high_52w": None, "low_52w": None}, weight=None, raw_qty=1)
    assert amber["color"] == "amber"


@pytest.mark.asyncio
async def test_portfolio_has_signal():
    async with _client() as c:
        h = await auth_headers(c, "sig@example.com")
        await c.post("/api/investments", json={"tx_type": "buy", "symbol": "TSLA", "quantity": 10, "price": 100, "currency": "USD"}, headers=h)
        await c.post("/api/investments/quotes/ingest", json={"quotes": [
            {"symbol": "TSLA", "price": 180, "currency": "USD", "high_52w": 185, "low_52w": 90}]}, headers=TOKEN)
        d = (await c.get("/api/investments/portfolio", headers=h)).json()
        sig = d["holdings"][0]["signal"]
        assert sig["color"] in ("red", "amber", "green")
        assert "pos_52w" in sig


@pytest.mark.asyncio
async def test_tax_timetest():
    from datetime import datetime
    old = datetime.utcnow().replace(year=datetime.utcnow().year - 4).date().isoformat()  # >3 roky
    recent = datetime.utcnow().date().isoformat()
    async with _client() as c:
        h = await auth_headers(c, "tax@example.com")
        await c.post("/api/investments", json={"tx_type": "buy", "symbol": "AAPL", "quantity": 5, "price": 100, "currency": "USD", "executed_at": old}, headers=h)
        await c.post("/api/investments", json={"tx_type": "buy", "symbol": "MSFT", "quantity": 2, "price": 300, "currency": "USD", "executed_at": recent}, headers=h)
        d = (await c.get("/api/investments/timetest", headers=h)).json()
    lots = {l["symbol"]: l for l in d["lots"]}
    assert lots["AAPL"]["tax_free"] is True
    assert lots["MSFT"]["tax_free"] is False
    assert 1000 < lots["MSFT"]["days_remaining"] <= 1096  # ~3 roky
    assert d["summary"]["n_tax_free"] == 1 and d["summary"]["n_pending"] == 1


@pytest.mark.asyncio
async def test_timetest_fifo_reduces_sold():
    from datetime import datetime
    old = datetime.utcnow().replace(year=datetime.utcnow().year - 4).date().isoformat()
    async with _client() as c:
        h = await auth_headers(c, "tax2@example.com")
        await c.post("/api/investments", json={"tx_type": "buy", "symbol": "NVDA", "quantity": 10, "price": 50, "currency": "USD", "executed_at": old}, headers=h)
        await c.post("/api/investments", json={"tx_type": "sell", "symbol": "NVDA", "quantity": 4, "price": 100, "currency": "USD", "executed_at": datetime.utcnow().date().isoformat()}, headers=h)
        d = (await c.get("/api/investments/timetest", headers=h)).json()
    nvda = [l for l in d["lots"] if l["symbol"] == "NVDA"]
    assert len(nvda) == 1 and nvda[0]["quantity"] == 6  # 10 − 4 prodáno (FIFO)


@pytest.mark.asyncio
async def test_curve():
    from datetime import date, timedelta
    async with _client() as c:
        h = await auth_headers(c, "curve@example.com")
        buy_day = (date.today() - timedelta(days=10)).isoformat()
        await c.post("/api/investments", json={"tx_type": "buy", "symbol": "AAPL", "quantity": 10, "price": 100, "currency": "USD", "executed_at": buy_day}, headers=h)
        # historie close + FX
        bars = [{"date": (date.today() - timedelta(days=d)).isoformat(), "close": 150} for d in range(12)]
        await c.post("/api/investments/prices/history", json={"symbol": "AAPL", "bars": bars}, headers=TOKEN)
        await c.post("/api/investments/quotes/ingest", json={"quotes": [{"symbol": "USDCZK", "price": 20}]}, headers=TOKEN)
        d = (await c.get("/api/investments/curve?days=30&base=CZK", headers=h)).json()
    assert d["points"], "žádné body"
    last = d["points"][-1]
    assert abs(last["invested"] - 10 * 100 * 20) < 50     # cost × FX
    assert abs(last["value"] - 10 * 150 * 20) < 50        # qty × close × FX
    assert d["complete"] is True


@pytest.mark.asyncio
async def test_curve_requires_auth():
    async with _client() as c:
        assert (await c.get("/api/investments/curve")).status_code == 401


@pytest.mark.asyncio
async def test_symbols_internal_only():
    async with _client() as c:
        h = await auth_headers(c, "inv3@example.com")
        await c.post("/api/investments", json={"tx_type": "buy", "symbol": "nvda", "quantity": 1, "price": 100, "currency": "USD"}, headers=h)
        assert (await c.get("/api/investments/symbols")).status_code in (401, 403)
        r = await c.get("/api/investments/symbols", headers=TOKEN)
        assert r.status_code == 200
        assert "NVDA" in r.json()["symbols"]
