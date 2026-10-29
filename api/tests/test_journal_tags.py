"""Deník: tagy, strategie, chyby u ztrát a statistiky podle podmínek obchodu."""
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


@pytest.mark.asyncio
async def test_default_tags_and_strategy_stats():
    async with _client() as c:
        h = await auth_headers(c, "t@x.cz")
        d = (await c.get("/api/journal/tags", headers=h)).json()
        by = {(t["kind"], t["name"]): t["id"] for t in d["tags"]}
        assert {("setup", "FVG"), ("setup", "iFVG"), ("setup", "OB"), ("setup", "Fibo OTE"),
                ("setup", "Liquidity"), ("timeframe", "M5")} <= set(by)
        # druhé volání nic nezdvojí
        assert len((await c.get("/api/journal/tags", headers=h)).json()["tags"]) == len(d["tags"])

        liq, ifvg, m5 = by[("setup", "Liquidity")], by[("setup", "iFVG")], by[("timeframe", "M5")]
        fomo = by[("mistake", "Vstup před OTE (FOMO)")]
        st = (await c.post("/api/journal/strategies", json={"name": "Sweep + iFVG", "tag_ids": [liq, ifvg, m5, fomo]},
                           headers=h)).json()["strategy"]
        assert st["tag_ids"] == [liq, ifvg, m5]   # mistake tag do strategie nepatří

        base = {"instrument": "NQ", "direction": "long", "strategy_id": st["id"], "tag_ids": [liq, ifvg, m5]}
        await c.post("/api/journal", json={**base, "outcome": "win", "r_result": 3}, headers=h)
        await c.post("/api/journal", json={**base, "outcome": "win", "r_result": 2}, headers=h)
        r = await c.post("/api/journal", json={**base, "outcome": "loss", "r_result": -1, "mistake_ids": [fomo, liq],
                                               "loss_reason": "Vstoupil jsem před OTE"}, headers=h)
        e = r.json()["entry"]
        assert e["mistake_ids"] == [fomo] and e["loss_reason"] == "Vstoupil jsem před OTE"

        s = (await c.get("/api/journal/stats", headers=h)).json()
        assert s["by_strategy"][0] == {"key": "Sweep + iFVG", "n": 3, "win_rate": 67, "avg_r": 1.33}
        assert {b["key"]: b["n"] for b in s["by_tag"]} == {"Liquidity": 3, "iFVG": 3}
        assert s["by_timeframe"][0]["key"] == "M5"
        assert s["by_combo"][0]["key"] == "Liquidity + iFVG + M5"
        assert s["by_mistake"] == [{"key": "Vstup před OTE (FOMO)", "n": 1, "r_lost": -1.0}]
        assert s["losses"] == {"total": 1, "explained": 1}

        # smazání tagu ho odebere z obchodů i strategie; smazání strategie obchody nechá
        assert (await c.delete(f"/api/journal/tags/{ifvg}", headers=h)).status_code == 200
        entries = (await c.get("/api/journal", headers=h)).json()["entries"]
        assert all(ifvg not in x["tag_ids"] for x in entries)
        assert (await c.delete(f"/api/journal/strategies/{st['id']}", headers=h)).status_code == 200
        entries = (await c.get("/api/journal", headers=h)).json()["entries"]
        assert len(entries) == 3 and all(x["strategy_id"] is None for x in entries)


@pytest.mark.asyncio
async def test_tags_are_private_and_unique():
    async with _client() as c:
        a = await auth_headers(c, "a@x.cz")
        b = await auth_headers(c, "b@x.cz")
        mine = (await c.post("/api/journal/tags", json={"kind": "setup", "name": "  Breaker  "}, headers=a)).json()["tag"]
        assert mine["name"] == "Breaker"
        assert (await c.post("/api/journal/tags", json={"kind": "setup", "name": "breaker"}, headers=a)).status_code == 409
        assert (await c.post("/api/journal/tags", json={"kind": "bogus", "name": "x"}, headers=a)).status_code == 422
        # cizí tag nejde přejmenovat/smazat ani přiřadit k obchodu
        assert (await c.patch(f"/api/journal/tags/{mine['id']}", json={"name": "x"}, headers=b)).status_code == 404
        assert (await c.delete(f"/api/journal/tags/{mine['id']}", headers=b)).status_code == 404
        e = (await c.post("/api/journal", json={"instrument": "ES", "tag_ids": [mine["id"]]}, headers=b)).json()["entry"]
        assert e["tag_ids"] == []
        assert (await c.patch(f"/api/journal/tags/{mine['id']}", json={"name": "Breaker block"}, headers=a)).json()["tag"]["name"] == "Breaker block"


@pytest.mark.asyncio
async def test_strategy_journal_and_rule_compliance():
    async with _client() as c:
        h = await auth_headers(c, "s@x.cz")
        by = {(t["kind"], t["name"]): t["id"] for t in (await c.get("/api/journal/tags", headers=h)).json()["tags"]}
        liq, ob, ifvg, smt, ote = (by[("setup", n)] for n in ("Liquidity", "OB", "iFVG", "SMT", "Fibo OTE"))
        rules = {"blocks": [
            {"id": "h1", "tf": "H1", "label": "kontext", "conds": [
                {"id": "liq", "tag_id": liq, "action": "vybrána (sweep)", "req": "must"},
                {"id": "ob", "tag_id": ob, "obj_tf": "H4", "action": "zasažen", "req": "must"}]},
            {"id": "m5", "tf": "M5", "conds": [
                {"id": "ifvg", "tag_id": ifvg, "action": "vznikl", "req": "must"},
                {"id": "liq5", "tag_id": liq, "req": "A"},
                {"id": "smt", "tag_id": smt, "req": "A"},
                {"id": "ote", "tag_id": ote, "req": "opt"},
                {"id": "x", "tag_id": by[("mistake", "Revenge trade")], "req": "must"}]},   # chyba do pravidel nepatří
        ]}
        st = (await c.post("/api/journal/strategies", json={"name": "Sweep", "rules": rules}, headers=h)).json()["strategy"]
        assert [len(b["conds"]) for b in st["blocks"]] == [2, 4]
        assert st["blocks"][0]["conds"][1]["obj_tf"] == "H4" and sorted(st["tag_ids"]) == sorted([liq, ob, ifvg, smt, ote])
        assert (await c.post("/api/journal/strategies", json={"name": "X", "rules": {"blocks": [{"tf": "H2"}]}},
                             headers=h)).status_code == 422
        other = (await c.post("/api/journal/strategies", json={"name": "Jiná", "rules": {"blocks": []}}, headers=h)).json()["strategy"]
        base = {"instrument": "NQ", "strategy_id": st["id"]}
        ok = ["liq", "ob", "ifvg"]
        await c.post("/api/journal", json={**base, "checks": ok + ["smt", "ote"], "r_result": 3}, headers=h)
        await c.post("/api/journal", json={**base, "checks": ok + ["liq5"], "r_result": 2}, headers=h)
        await c.post("/api/journal", json={**base, "checks": ["ob", "ifvg", "smt"], "r_result": -1}, headers=h)  # bez sweepu
        await c.post("/api/journal", json={**base, "checks": ok, "r_result": -1}, headers=h)   # chybí skupina A
        await c.post("/api/journal", json={"instrument": "ES", "strategy_id": other["id"], "r_result": -1}, headers=h)

        s = (await c.get("/api/journal/stats", headers=h)).json()
        assert s["compliance"] is None and s["totals"]["trades"] == 5
        j = {x["name"]: x for x in s["strategies"]}
        assert j["Sweep"]["n"] == 4 and j["Sweep"]["compliance"] == 50 and j["Sweep"]["sum_r"] == 3
        assert j["Jiná"]["compliance"] is None   # strategie bez pravidel

        comp = (await c.get(f"/api/journal/stats?strategy_id={st['id']}", headers=h)).json()["compliance"]
        assert comp["rules_total"] == 4   # 3 povinné + skupina A
        assert {b["key"]: (b["n"], b["win_rate"]) for b in comp["buckets"]} == {"all": (2, 100), "broken": (2, 0)}
        assert comp["by_rule"] == [{"key": "H1 · Liquidity vybrána (sweep)", "n": 1, "win_rate": 0, "avg_r": -1.0}]
        assert {b["key"]: b["n"] for b in comp["optional"]} == {"✓ M5 · Fibo OTE": 1, "✗ M5 · Fibo OTE": 3}
        assert {b["key"]: b["n"] for b in comp["alternatives"]} == {"A: M5 · Liquidity": 1, "A: M5 · SMT": 2}

        # cizí strategie
        b = await auth_headers(c, "z@x.cz")
        assert (await c.get(f"/api/journal/stats?strategy_id={st['id']}", headers=b)).status_code == 404


@pytest.mark.asyncio
async def test_legacy_strategy_converts_to_block():
    async with _client() as c:
        h = await auth_headers(c, "l@x.cz")
        by = {(t["kind"], t["name"]): t["id"] for t in (await c.get("/api/journal/tags", headers=h)).json()["tags"]}
        st = (await c.post("/api/journal/strategies", json={"name": "Old", "tag_ids": [by[("setup", "OB")], by[("timeframe", "H1")]]},
                           headers=h)).json()["strategy"]
        assert st["blocks"] == [{"id": "b0", "tf": "H1", "label": None, "conds": [
            {"id": f"t{by[('setup', 'OB')]}", "tag_id": by[("setup", "OB")], "action": None, "obj_tf": None, "req": "must"}]}]
        await c.post("/api/journal", json={"instrument": "NQ", "strategy_id": st["id"], "tag_ids": [by[("setup", "OB")]], "r_result": 1}, headers=h)
        s = (await c.get("/api/journal/stats", headers=h)).json()
        assert s["strategies"][0]["compliance"] == 100
