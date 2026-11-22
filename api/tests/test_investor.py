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


# ── volné peníze, investiční typ, minimální nákup ───────────────────────────
def test_aggressive_plan_and_min_order():
    t = P.plan_targets("aggressive")
    assert sum(t.values()) == 100 and t["stocks"] == 45 and t["bonds"] == 0
    # malý vklad se nerozdrobí na položky pod 500 Kč
    alloc = P.allocation([], P.plan_targets("careful"))
    out = P.split_contribution(alloc, P.plan_targets("careful"), 1500)
    assert sum(out.values()) == 1500 and all(v >= P.MIN_ORDER_CZK for v in out.values())


def test_capital_hint():
    assert P.capital_hint(5_000, 5_000, "calm") is None
    assert "najednou" in P.capital_hint(200_000, 5_000, "calm")
    assert "nervózní" in P.capital_hint(200_000, 5_000, "panic")


@pytest.mark.asyncio
async def test_capital_spent_by_new_buys():
    async with _client() as c:
        h = await auth_headers(c, "kapital@example.com")
        await c.post("/api/investments/quotes/ingest", json={"quotes": [
            {"symbol": "VWCE.DE", "price": 100, "currency": "EUR"}, {"symbol": "EURCZK", "price": 25}]}, headers=TOKEN)
        # starý nákup z importu (před zadáním částky) se od volných peněz neodečítá
        old = (datetime.utcnow() - timedelta(days=400)).date().isoformat()
        await c.post("/api/investments", json={"tx_type": "buy", "symbol": "VWCE.DE", "quantity": 10, "price": 100,
                                               "currency": "EUR", "executed_at": old}, headers=h)
        d = (await c.put("/api/investor/profile", json={"capital_czk": 100_000, "monthly_czk": 5000}, headers=h)).json()
        assert d["capital_czk"] == 100_000 and d["capital_left"] == 100_000 and d["plan_set"] is False
        plan = (await c.get("/api/investor/plan", headers=h)).json()
        assert plan["invest_now"]["total"] == 105_000 and plan["invest_now"]["hint"]
        assert sum(x["amount"] for x in plan["contribution"]) == 105_000
        # nový nákup 20 ks × 100 EUR × 25 = 50 000 Kč → zbývá 50 000
        today = datetime.utcnow().date().isoformat()
        await c.post("/api/investments", json={"tx_type": "buy", "symbol": "VWCE.DE", "quantity": 20, "price": 100,
                                               "currency": "EUR", "executed_at": today}, headers=h)
        d = (await c.get("/api/investor/profile", headers=h)).json()
        assert d["capital_left"] == pytest.approx(50_000)
        plan = (await c.get("/api/investor/plan", headers=h)).json()
        assert plan["invest_now"]["capital"] == pytest.approx(50_000)
        # volba typu se pamatuje
        d = (await c.put("/api/investor/profile", json={"plan": "aggressive"}, headers=h)).json()
        assert d["plan_set"] is True and d["targets"]["stocks"] == 45 and d["capital_left"] == pytest.approx(50_000)


def test_small_portfolio_defers_stocks_and_big_buy_splits():
    c, deferred = P.fit_to_size({"world": 3000, "stocks": 2000}, total_after=20_000)
    assert deferred and c == {"world": 5000}
    c, deferred = P.fit_to_size({"world": 3000, "stocks": 2000}, total_after=500_000)
    assert not deferred and c["stocks"] == 2000
    ideas = [{"ticker": t, "name": t} for t in ("AAA", "BBB", "CCC", "DDD")]
    held = [_pos("AAA.US", "stocks", 1000, 1, "amber")]          # držená (ne zelená) se z Nápadů nenabízí
    picks = P.stock_picks(held, ideas, 210_000)
    assert [p[0] for p in picks] == ["BBB", "CCC", "DDD"] and sum(p[2] for p in picks) == 210_000
    assert len(P.stock_picks([], ideas, 8_000)) == 1
    alloc = P.allocation([], P.plan_targets("aggressive"))
    acts = P.build_actions(positions=[], alloc=alloc, targets=P.plan_targets("aggressive"),
                           contribution={"world": 55_000, "stocks": 45_000}, lots=[], ideas=ideas, prices_czk={})
    assert [a["symbol"] for a in acts if a["kind"] == "buy" and a["cls"] == "stocks"] == ["AAA", "BBB"]


# ── jednoduchý Radar ────────────────────────────────────────────────────────
from app.services import company_explain as X  # noqa: E402


def test_company_reasons_are_plain_czech():
    assert "levnější než obvykle" in X.reason("pctile_pe_fwd", 20)
    assert "80 %" in X.reason("pctile_pe_fwd", 20)
    assert X.reason("net_debt_to_ebitda", -0.4) == "Má víc hotovosti než dluhů."
    assert "Skupuje vlastní akcie" in X.reason("share_count_change", -2.5)
    assert "klesnout" in X.reason("eps_growth_ntm", -12)
    assert X.reason("roic", None) is None
    v = X.explain(scores={"valuation": 75, "growth": 65, "quality": 30, "revision": None, "trend": 50},
                  metrics={"pctile_pe_fwd": 20, "eps_growth_ntm": 18, "fcf_margin": 25},
                  drivers={"positive": [{"name": "P/E fwd vs. historie", "value": 20, "contribution": 6}],
                           "negative": [{"name": "zadlužení", "value": 3.5, "contribution": -2}]},
                  verdict="LEVNÁ", horizon="SPÍŠE ANO", bubble=False, confidence=0.9, growth_basis="ntm")
    assert v["bucket"] == "cheap" and v["zone"] == "buy" and v["reliable"]
    assert [p["level"] for p in v["pillars"]] == ["good", "good", "weak", "none", "ok"]
    assert v["pros"][0].startswith("Vůči ziskům") and "vysoký" in v["cons"][0]


def test_company_advice_respects_plan_and_weight():
    a = X.advice(bucket_="cheap", zone_="buy", reliable=True, held_weight=None, stocks_target=45, plan_label="Agresivní")
    assert a["kind"] == "buy"
    assert X.advice(bucket_="cheap", zone_="buy", reliable=True, held_weight=12, stocks_target=45, plan_label="x")["kind"] == "hold"
    a = X.advice(bucket_="cheap", zone_="buy", reliable=True, held_weight=None, stocks_target=0, plan_label="Opatrný")
    assert "Opatrný" in a["text"] and a["kind"] == "hold"
    assert X.advice(bucket_="expensive", zone_="avoid", reliable=True, held_weight=None, stocks_target=30, plan_label="x")["kind"] == "wait"
    assert X.advice(bucket_="expensive", zone_="avoid", reliable=True, held_weight=15, stocks_target=30, plan_label="x")["kind"] == "trim"


@pytest.mark.asyncio
async def test_radar_endpoints():
    from datetime import date
    from sqlalchemy import update
    from app.config import settings
    from app.db.session import session_context
    from app.models import User
    from app.valuation.models import ValInstrument, ValMetricsDaily, ValOverviewSnapshot, ValScoreDaily
    async with _client() as c:
        h = await auth_headers(c, "radar@example.com")
        old_free = settings.free_access
        settings.free_access = False
        try:
            assert (await c.get("/api/investor/radar", headers=h)).status_code == 403    # tarif jako plný Radar
            async with session_context() as s:
                await s.execute(update(User).where(User.email == "radar@example.com").values(plan="trader"))
                s.add(ValInstrument(ticker="ACME", name="Acme Corp", gics_sector="Technology"))
                s.add(ValScoreDaily(ticker="ACME", as_of_date=date(2026, 11, 20), valuation_score=72, growth_score=60,
                                    quality_score=55, revision_score=50, trend_score=45, composite_score=60,
                                    valuation_verdict="LEVNÁ", horizon_verdict="SPÍŠE ANO", confidence=0.9,
                                    drivers={"positive": [{"name": "růst EPS (NTM)", "value": 15, "contribution": 4}], "negative": []},
                                    model_version=settings.val_model_version))
                s.add(ValMetricsDaily(ticker="ACME", as_of_date=date(2026, 11, 20), model_version=settings.val_model_version,
                                      metrics={"pctile_pe_fwd": 25, "eps_growth_ntm": 15}))
                s.add(ValOverviewSnapshot(name="latest", as_of_date=date(2026, 11, 20), payload={"items": [
                    {"ticker": "ACME", "name": "Acme Corp", "valuation_verdict": "LEVNÁ", "pctile_pe_fwd": 25,
                     "eps_growth_ntm": 15, "confidence": 0.9, "growth_basis": "ntm", "market_cap": 1e9}]}))
                await s.commit()
            d = (await c.get("/api/investor/radar", headers=h)).json()
            assert d["items"][0]["bucket"] == "cheap" and d["items"][0]["held"] is False
            assert d["items"][0]["pctile_pe_fwd"] == 25 and d["zones"]["buy"]          # data pro mapu zón
            r = await c.get("/api/investor/radar/acme", headers=h)
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["name"] == "Acme Corp" and d["verdict_label"] == "Levná" and len(d["pillars"]) == 5
            assert d["pros"] and d["advice"]["kind"] == "buy"         # výchozí typ Vyvážený má 15 % akcií
            assert (await c.get("/api/investor/radar/NOPE", headers=h)).status_code == 404
        finally:
            settings.free_access = old_free
