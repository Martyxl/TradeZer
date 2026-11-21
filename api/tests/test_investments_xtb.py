"""Import výpisu z XTB (xlsx) + prodej z konkrétního nákupu (celý / částečný)."""
import base64
import io
import os
from datetime import datetime

import pytest

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.engine import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services.xtb_import import holdings_check, instrument_currency, parse_xtb  # noqa: E402
from tests._auth import auth_headers  # noqa: E402


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _xlsx(extra_ops=()) -> bytes:
    """Syntetický výpis ve formátu XTB (stejné listy, hlavičky a komentáře)."""
    import openpyxl
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    cp = wb.create_sheet("Closed Positions")
    cp.append(["Account number", "123"])
    co = wb.create_sheet("Cash Operations")
    for r in (["Account number", "123"], ["Cash Operations", ""], ["Date from (UTC)", datetime(2006, 1, 1)],
              ["Date to (UTC)", datetime(2026, 11, 21)],
              ["Type", "Instrument", "Ticker", "Category", "Time", "Amount", "ID", "Comment", "Product", "Position ID"]):
        co.append(r)
    ops = [
        ["Deposit", "", "", "", datetime(2026, 9, 1, 10), 100000.0, "1", "deposit", "My Trades", ""],
        ["Stock purchase", "Nvidia", "NVDA.US", "STOCK", datetime(2026, 9, 2, 15), -12800.0, "2",
         "OPEN BUY NVDA.US 4/5 @ 140.00", "My Trades", "P1"],
        ["Stock purchase", "Nvidia", "NVDA.US", "STOCK", datetime(2026, 9, 2, 15), -3200.0, "3",
         "OPEN BUY 1/5 @ 140.50", "My Trades", "P1"],                       # starší formát bez tickeru
        ["Stock sell", "Nvidia", "NVDA.US", "STOCK", datetime(2026, 9, 9, 15), 7000.0, "4",
         "CLOSE BUY NVDA.US 2/2 @ 150.00", "My Trades", "P1"],
        ["Stock purchase", "Core S&P 500", "SXR8.DE", "ETF", datetime(2026, 9, 3, 8), -15000.0, "5",
         "OPEN BUY SXR8.DE 1 @ 600.00", "Investment Plans", "P2"],
        ["Stock purchase", "World", "VWRA.UK", "ETF", datetime(2026, 9, 3, 8), -2760.0, "6",
         "OPEN BUY VWRA.UK 1 @ 120.00", "Investment Plans", "P3"],           # .UK v USD (kurz ~23)
        ["Dividend", "Nvidia", "NVDA.US", "STOCK", datetime(2026, 10, 1), 50.0, "7", "NVDA.US USD 0.01/ SHR", "My Trades", ""],
        ["Withholding tax", "Nvidia", "NVDA.US", "STOCK", datetime(2026, 10, 1), -7.5, "8", "NVDA.US USD WHT 15%", "My Trades", ""],
        ["Subaccount transfer", "", "", "", datetime(2026, 9, 1, 11), -10000.0, "9", "Transfer", "My Trades", ""],
        ["Close trade", "", "DE30", "", datetime(2026, 9, 5), 130.0, "10", "Profit of position #1", "My Trades", ""],
        ["Free funds interest", "", "", "", datetime(2026, 10, 3), 250.0, "11", "Free-funds Interest 2026-09", "My Trades", ""],
        *extra_ops,
    ]
    for r in ops:
        co.append(r)
    co.append(["Total", 0])
    op = wb.create_sheet("Open Positions")
    for r in (["Account number", "123"], ["Product", "Metric", "Amount", "Currency"],
              ["My Trades", "Open position value", 1.0, "CZK"], [],
              ["Product", "Instrument/Position", "Ticker", "Category", "Type", "Volume"],
              ["My Trades", "Nvidia", "NVDA.US", "STOCK", "", 3.0],
              ["My Trades", "x", "NVDA.US", "", "BUY", 3.0],
              ["Investment Plans", "y", "SXR8.DE", "", "BUY", 1.0],
              ["Investment Plans", "z", "VWRA.UK", "", "BUY", 1.0]):
        op.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parser_maps_operations_and_checks_open_positions():
    p = parse_xtb(_xlsx())
    types = [r["tx_type"] for r in p["rows"]]
    assert types.count("buy") == 4 and types.count("sell") == 1 and types.count("dividend") == 2
    assert "interest" in types and "deposit" in types
    assert p["skipped"] == {"převod mezi vlastními podúčty": 1, "CFD obchod": 1}
    nv = [r for r in p["rows"] if r["symbol"] == "NVDA" and r["tx_type"] == "buy"]
    assert [(r["quantity"], r["price"], r["currency"]) for r in nv] == [(4.0, 140.0, "USD"), (1.0, 140.5, "USD")]
    assert {r["symbol"]: r["currency"] for r in p["rows"] if r["tx_type"] == "buy"}["VWRA.UK"] == "USD"
    assert holdings_check(p["rows"], p["open_positions"]) == []
    assert instrument_currency("X.UK", "CZK", 29.5) == "GBP"


def test_parser_rejects_other_files():
    with pytest.raises(ValueError):
        parse_xtb(b"not an excel")


@pytest.mark.asyncio
async def test_import_dry_run_then_import_dedup_and_legacy():
    body = {"content_b64": base64.b64encode(_xlsx()).decode(), "source": "xtb.xlsx"}
    async with _client() as c:
        h = await auth_headers(c, "x@t.cz")
        # dřívější import (bez ID operace) → nabídne se nahrazení
        await c.post("/api/investments", json={"tx_type": "buy", "symbol": "NVDA", "quantity": 5, "price": 140,
                                               "broker": "xtb"}, headers=h)
        dry = (await c.post("/api/investments/import/xtb", json={**body, "dry_run": True}, headers=h)).json()
        assert dry["new"] == 9 and dry["legacy"] == 1 and dry["check"] == [] and "created" not in dry
        assert len((await c.get("/api/investments", headers=h)).json()["transactions"]) == 1

        r = (await c.post("/api/investments/import/xtb", json={**body, "replace_legacy": True}, headers=h)).json()
        assert r["created"] == 9 and r["replaced_legacy"] == 1
        again = (await c.post("/api/investments/import/xtb", json=body, headers=h)).json()
        assert again["new"] == 0 and again["created"] == 0

        txs = (await c.get("/api/investments", headers=h)).json()["transactions"]
        sell = next(t for t in txs if t["tx_type"] == "sell")
        lot = next(t for t in txs if t["id"] == sell["lot_id"])
        assert lot["quantity"] == 4 and lot["status"] == "partial" and lot["remaining"] == 2
        assert sell["realized"] == 20.0                                  # (150 − 140) × 2
        pf = (await c.get("/api/investments/portfolio", headers=h)).json()
        qty = {x["symbol"]: x["quantity"] for x in pf["holdings"]}
        assert qty["NVDA"] == 3 and qty["SXR8.DE"] == 1


@pytest.mark.asyncio
async def test_sell_full_and_partial_lot():
    async with _client() as c:
        h = await auth_headers(c, "s@t.cz")
        a = (await c.post("/api/investments", json={"tx_type": "buy", "symbol": "MSFT", "quantity": 10, "price": 400,
                                                    "currency": "USD", "executed_at": "2026-01-05", "fee": 2}, headers=h)).json()
        b = (await c.post("/api/investments", json={"tx_type": "buy", "symbol": "MSFT", "quantity": 2, "price": 420,
                                                    "currency": "USD", "executed_at": "2026-02-05"}, headers=h)).json()
        # částečný prodej 4 z 10: původní nákup → 6, oddělená část 4 (uzavřená) + prodej 4
        r = (await c.post(f"/api/investments/{a['id']}/sell", json={"quantity": 4, "price": 450,
                                                                     "executed_at": "2026-03-01"}, headers=h)).json()
        assert r["status"] == "partial" and r["remaining"] == 6
        txs = {t["id"]: t for t in (await c.get("/api/investments", headers=h)).json()["transactions"]}
        assert txs[a["id"]]["quantity"] == 6 and txs[a["id"]]["status"] == "open" and txs[a["id"]]["fee"] == 1.2
        split = txs[r["split_id"]]
        assert split["quantity"] == 4 and split["status"] == "closed" and split["price"] == 400
        s = txs[r["sell_id"]]
        assert s["tx_type"] == "sell" and s["lot_id"] == split["id"] and s["realized"] == 200.0
        # celý zbytek druhého nákupu → jen nový řádek prodeje
        r2 = (await c.post(f"/api/investments/{b['id']}/sell", json={"price": 410}, headers=h)).json()
        assert r2["status"] == "closed" and r2["split_id"] is None
        assert (await c.post(f"/api/investments/{b['id']}/sell", json={"price": 410}, headers=h)).status_code == 400
        assert (await c.post(f"/api/investments/{a['id']}/sell", json={"quantity": 7, "price": 1}, headers=h)).status_code == 400
        pf = (await c.get("/api/investments/portfolio", headers=h)).json()
        assert {x["symbol"]: x["quantity"] for x in pf["holdings"]}["MSFT"] == 6
        # cizí uživatel nemůže prodat můj nákup
        h2 = await auth_headers(c, "o@t.cz")
        assert (await c.post(f"/api/investments/{a['id']}/sell", json={"price": 1}, headers=h2)).status_code == 404


@pytest.mark.asyncio
async def test_portfolio_shows_brokers_per_position():
    async with _client() as c:
        h = await auth_headers(c, "b@t.cz")
        for broker, q in (("xtb", 3), ("etoro", 1.5), ("xtb", 1)):
            await c.post("/api/investments", json={"tx_type": "buy", "symbol": "COIN", "quantity": q, "price": 100,
                                                   "broker": broker}, headers=h)
        await c.post("/api/investments", json={"tx_type": "buy", "symbol": "AAPL", "quantity": 2, "price": 100,
                                               "broker": "etoro"}, headers=h)
        await c.post("/api/investments", json={"tx_type": "sell", "symbol": "AAPL", "quantity": 2, "price": 120,
                                               "broker": "etoro"}, headers=h)
        pf = (await c.get("/api/investments/portfolio", headers=h)).json()
        coin = next(x for x in pf["holdings"] if x["symbol"] == "COIN")
        assert coin["brokers"] == [{"broker": "xtb", "quantity": 4}, {"broker": "etoro", "quantity": 1.5}]
        assert all(x["symbol"] != "AAPL" for x in pf["holdings"])
