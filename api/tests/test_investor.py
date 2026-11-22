"""Jednoduchý režim (Začátečník): třídění aktiv, plány, rozdělení vkladu, pravidla akcí a endpointy."""
import os
from datetime import datetime, timedelta

import pytest

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["ANTHROPIC_API_KEY"] = "test-key"
os.environ["INTERNAL_API_TOKEN"] = "test-token"

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.base import Base
from app.db.engine import engine
from app.services import investor_plan as P
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


# ── čisté funkce ────────────────────────────────────────────────────────────
def test_classify():
    assert P.classify("VWCE.DE") == "world"
    assert P.classify("CSPX.UK") == "world"          # XTB suffix
    assert P.classify("4GLD.DE") == "gold"
    assert P.classify("EUNA.DE") == "bonds"
    assert P.classify("XEON.DE") == "cash"
    assert P.classify("AAPL.US") == "stocks"
    assert P.classify("FOO.DE", "Some Physical Gold ETC") == "gold"
    assert P.classify("BAR.L", "iShares Euro Govt Bond UCITS ETF") == "bonds"
    assert P.classify("BAZ.L", "Acme MSCI Europe UCITS ETF") == "world"
    assert P.classify("QQQX", None, {"type": "ETF"}) == "world"


def test_plan_targets_and_custom_validation():
    assert sum(P.plan_targets("careful").values()) == 100
    assert P.plan_targets("nonsense") == P.PLANS["balanced"]["targets"]
    t = P.plan_targets("custom", {"world": 80, "gold": 20})
    assert t["world"] == 80 and t["gold"] == 20 and t["stocks"] == 0
    with pytest.raises(ValueError):
        P.validate_custom({"world": 50, "gold": 20})       # součet ≠ 100
    with pytest.raises(ValueError):
        P.validate_custom({"world": 120, "gold": -20})


def test_split_contribution_fills_gaps_without_selling():
    targets = {"world": 60, "bonds": 15, "gold": 10, "cash": 0, "stocks": 15}
    pos = [{"symbol": "VWCE.DE", "cls": "world", "value_base": 52_000},
           {"symbol": "4GLD.DE", "cls": "gold", "value_base": 6_000},
           {"symbol": "EUNA.DE", "cls": "bonds", "value_base": 12_000},
           {"symbol": "AAPL", "cls": "stocks", "value_base": 30_000}]
    alloc = P.allocation(pos, targets)
    assert alloc["total"] == 100_000
    split = P.split_contribution(alloc, targets, 5000)
    assert sum(split.values()) == 5000
    assert "stocks" not in split                      # akcie jsou nad cílem → do nich nic
    assert split["world"] > split["gold"] > 0
    # prázdné portfolio → podle cílových vah
    empty = P.allocation([], targets)
    s0 = P.split_contribution(empty, targets, 10_000)
    assert s0 == {"world": 6000, "bonds": 1500, "gold": 1000, "stocks": 1500}


def test_allocation_counts_reserve_and_unpriced():
    targets = P.plan_targets("careful")
    a = P.allocation([{"symbol": "X", "cls": "world", "value_base": None},
                      {"symbol": "VWCE.DE", "cls": "world", "value_base": 9000}], targets, reserve=1000)
    assert a["unpriced"] == ["X"]
    cash = {r["cls"]: r for r in a["classes"]}["cash"]
    assert cash["value"] == 1000 and cash["pct"] == 10.0


def _pos(sym, cls, value, weight, color="amber", qty=10, up=10.0, reasons=None, trim=None):
    return {"symbol": sym, "name": sym, "cls": cls, "value_base": value, "weight": weight, "quantity": qty,
            "unrealized_pct": up, "signal": {"color": color, "reasons": reasons or [], "trim_qty": trim}}


def test_actions_trim_wait_and_tax():
    targets = P.plan_targets("balanced")
    positions = [_pos("VWCE.DE", "world", 50_000, 50), _pos("NVDA", "stocks", 25_000, 25, "red", qty=20, up=140,
                                                          reasons=["velký zisk +140 %", "velká váha v portfoliu 25 %"], trim=12),
                 _pos("AAPL", "stocks", 15_000, 15, "red", up=40, reasons=["blízko 52T maxima", "velký zisk +60 %"]),
                 _pos("MSFT", "stocks", 10_000, 10)]
    alloc = P.allocation(positions, targets)
    lots = [{"symbol": "AAPL", "days_remaining": 20, "free_date": "2026-12-12", "tax_free": False},
            {"symbol": "NVDA", "days_remaining": -100, "free_date": "2026-01-01", "tax_free": True},
            {"symbol": "MSFT", "days_remaining": 10, "free_date": "2026-12-02", "tax_free": False}]
    acts = P.build_actions(positions=positions, alloc=alloc, targets=targets,
                           contribution=P.split_contribution(alloc, targets, 5000), lots=lots, ideas=[], prices_czk={})
    kinds = {(a["kind"], a.get("symbol")) for a in acts}
    assert ("trim", "NVDA") in kinds
    nvda = next(a for a in acts if a.get("symbol") == "NVDA")
    assert "12 ks" in nvda["text"] and "bez daně" in nvda["text"]
    assert ("wait", "AAPL") in kinds                   # červená, ale za 20 dní bez daně
    assert ("tax", "MSFT") in kinds                    # informace o blížícím se osvobození
    assert any(a["kind"] == "rebalance" and a["cls"] == "stocks" for a in acts)   # 50 % vs cíl 15 %
    assert acts[0]["kind"] == "buy"
    assert acts[-1]["kind"] == "hold"


def test_actions_stock_bucket_prefers_green_holding_then_idea():
    targets = {"world": 50, "bonds": 0, "gold": 0, "cash": 0, "stocks": 50}
    pos = [_pos("VWCE.DE", "world", 10_000, 90), _pos("GOOGL", "stocks", 1_000, 9, "green")]
    alloc = P.allocation(pos, targets)
    acts = P.build_actions(positions=pos, alloc=alloc, targets=targets,
                           contribution=P.split_contribution(alloc, targets, 2000), lots=[],
                           ideas=[{"ticker": "UNH", "name": "UnitedHealth"}], prices_czk={"GOOGL": 4000})
    buy = next(a for a in acts if a["kind"] == "buy" and a["cls"] == "stocks")
    assert buy["symbol"] == "GOOGL" and buy["units"] == 0.5
    acts2 = P.build_actions(positions=pos[:1], alloc=P.allocation(pos[:1], targets), targets=targets,
                            contribution={"stocks": 1000}, lots=[], ideas=[{"ticker": "UNH", "name": "UnitedHealth"}],
                            prices_czk={})
    assert next(a for a in acts2 if a["kind"] == "buy")["symbol"] == "UNH"


def test_market_block_texts():
    m = P.market_block({"state": "panic", "label": "Panika", "sentiment": {"score": 18.4, "as_of_date": "2026-11-20"}})
    assert m["regime"]["label"] == "Panika" and "Neprodávej" in m["regime"]["tip"]
    assert m["sentiment"]["score"] == 18 and m["sentiment"]["label"] == "extrémní strach"
    assert P.market_block(None) == {"regime": None, "sentiment": None}


def test_ideas_from_overview_filters():
    rows = [
        {"ticker": "GOOGL", "name": "Alphabet", "pctile_pe_fwd": 15, "eps_growth_ntm": 15, "confidence": 0.9,
         "valuation_verdict": "LEVNÁ", "bubble_flag": False, "growth_basis": "ntm", "market_cap": 2e12},
        {"ticker": "WEIRD", "name": "Weird", "pctile_pe_fwd": 5, "eps_growth_ntm": 300, "confidence": 0.9,
         "valuation_verdict": "LEVNÁ", "bubble_flag": False, "growth_basis": "ntm"},           # nespolehlivý růst
        {"ticker": "LOWC", "name": "Low", "pctile_pe_fwd": 5, "eps_growth_ntm": 20, "confidence": 0.3,
         "valuation_verdict": "LEVNÁ", "bubble_flag": False, "growth_basis": "ntm"},           # nízká důvěra
        {"ticker": "PLTR", "name": "Palantir", "pctile_pe_fwd": 99, "eps_growth_ntm": 30, "confidence": 0.8,
         "valuation_verdict": "PŘEPÁLENÁ", "bubble_flag": True, "growth_basis": "ntm", "market_cap": 4e11},
    ]
    out = P.ideas_from_overview(rows, held={"GOOGL"}, fund_buyers={"GOOGL": 3}, house={"GOOGL"})
    assert [i["ticker"] for i in out["cheap"]] == ["GOOGL"]
    assert out["cheap"][0]["tags"] == ["přikupují fondy (3)", "drží Tradezer fond", "máš v portfoliu"]
    assert "Levnější než obvykle" in out["cheap"][0]["text"]
    assert [i["ticker"] for i in out["expensive"]] == ["PLTR"]


# ── endpointy ───────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_profile_defaults_and_update():
    async with _client() as c:
        assert (await c.get("/api/investor/profile")).status_code == 401
        h = await auth_headers(c, "zac@example.com")
        d = (await c.get("/api/investor/profile", headers=h)).json()
        assert d["mode"] is None and d["plan"] == "balanced" and d["saved"] is False
        r = await c.put("/api/investor/profile", json={"mode": "simple", "plan": "careful", "monthly_czk": 3000}, headers=h)
        assert r.status_code == 200, r.text
        d = (await c.get("/api/investor/profile", headers=h)).json()
        assert d["mode"] == "simple" and d["plan"] == "careful" and d["monthly_czk"] == 3000
        assert d["targets"]["bonds"] == 35
        # vlastní plán
        r = await c.put("/api/investor/profile", json={"plan": "custom", "targets": {"world": 90, "gold": 10}}, headers=h)
        assert r.status_code == 200 and r.json()["targets"]["world"] == 90
        # validace
        assert (await c.put("/api/investor/profile", json={"mode": "expert"}, headers=h)).status_code == 422
        assert (await c.put("/api/investor/profile", json={"monthly_czk": -5}, headers=h)).status_code == 422
        assert (await c.put("/api/investor/profile", json={"plan": "custom", "targets": {"world": 50}}, headers=h)).status_code == 422
        # profil je per-uživatel
        h2 = await auth_headers(c, "jiny@example.com")
        assert (await c.get("/api/investor/profile", headers=h2)).json()["mode"] is None


@pytest.mark.asyncio
async def test_plan_endpoint_end_to_end():
    async with _client() as c:
        h = await auth_headers(c, "plan@example.com")
        old = (datetime.utcnow() - timedelta(days=4 * 365)).date().isoformat()
        soon = (datetime.utcnow() - timedelta(days=3 * 365 - 15)).date().isoformat()   # bez daně za ~15 dní
        for tx in (
            {"tx_type": "buy", "symbol": "VWCE.DE", "quantity": 100, "price": 100, "currency": "EUR", "executed_at": old},
            {"tx_type": "buy", "symbol": "NVDA", "quantity": 50, "price": 20, "currency": "USD", "executed_at": soon},
        ):
            assert (await c.post("/api/investments", json=tx, headers=h)).status_code == 200
        await c.post("/api/investments/quotes/ingest", json={"quotes": [
            {"symbol": "VWCE.DE", "price": 150, "currency": "EUR"},
            {"symbol": "NVDA", "price": 180, "currency": "USD", "high_52w": 185, "low_52w": 90},
            {"symbol": "4GLD.DE", "price": 100, "currency": "EUR"},
            {"symbol": "EURCZK", "price": 25}, {"symbol": "USDCZK", "price": 23},
        ]}, headers=TOKEN)
        await c.post("/api/regime/ingest", json={"state": "tension", "label": "Napětí",
                                                 "sentiment": {"score": 30, "as_of_date": "2026-11-21"}}, headers=TOKEN)
        await c.put("/api/investor/profile", json={"plan": "balanced", "monthly_czk": 10000}, headers=h)

        r = await c.get("/api/investor/plan", headers=h)
        assert r.status_code == 200, r.text
        d = r.json()
        # VWCE 15 000 EUR = 375 000 Kč; NVDA 9 000 USD = 207 000 Kč
        assert abs(d["totals"]["value"] - 582_000) < 5
        cls = {x["cls"]: x for x in d["allocation"]["classes"]}
        assert cls["world"]["pct"] == pytest.approx(64.4, abs=0.2)
        assert cls["stocks"]["pct"] == pytest.approx(35.6, abs=0.2)
        assert sum(x["amount"] for x in d["contribution"]) == 10000
        kinds = {(a["kind"], a.get("symbol")) for a in d["actions"]}
        assert ("wait", "NVDA") in kinds                     # červená (zisk + váha + 52T max), ale brzy bez daně
        gold = next(a for a in d["actions"] if a["kind"] == "buy" and a["cls"] == "gold")
        assert gold["symbol"] == "4GLD.DE" and gold["units"] is not None
        assert d["market"]["regime"]["label"] == "Napětí" and d["market"]["sentiment"]["label"] == "strach"
        pos = {p["symbol"]: p for p in d["positions"]}
        assert pos["NVDA"]["tag"] == "wait" and pos["VWCE.DE"]["tax_free_all"] is True


@pytest.mark.asyncio
async def test_ideas_endpoint_universe():
    async with _client() as c:
        h = await auth_headers(c, "ideas@example.com")
        await c.post("/api/investments/quotes/ingest", json={"quotes": [
            {"symbol": "VWCE.DE", "price": 160, "currency": "EUR"}, {"symbol": "EURCZK", "price": 25}]}, headers=TOKEN)
        r = await c.get("/api/investor/ideas", headers=h)
        assert r.status_code == 200, r.text
        d = r.json()
        vw = next(u for u in d["base"] if u["symbol"] == "VWCE.DE")
        assert vw["price_czk"] == 4000 and vw["class_label"] == "Akciové fondy (ETF)"
        assert d["cheap"] == [] and d["expensive"] == []
        # ETF ze základu se stahují i bez držení
        syms = (await c.get("/api/investments/symbols", headers=TOKEN)).json()["symbols"]
        assert {"VWCE.DE", "4GLD.DE", "EUNA.DE"} <= set(syms)
