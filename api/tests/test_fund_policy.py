"""Fond: ochrana před splašeným obchodováním — režim trhu, padající nůž, výjimečné prodeje (daně)."""
import os
import sqlite3
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "data"))
import risk_regime  # noqa: E402
import tradezer_fund as tf  # noqa: E402


# ── čisté funkce ──────────────────────────────────────────────────────────────
def test_sell_needs_thesis_break_not_just_low_score():
    assert tf.sell_decision(-9, "FÉROVÁ", -0.1, 2000, "calm") == (None, "")          # obrat bez přepálené valuace
    assert tf.sell_decision(5, "PŘEPÁLENÁ", 0.1, 2000, "calm") == (None, "")         # přepálená, ale signály drží
    assert tf.sell_decision(-9, "PŘEPÁLENÁ", -0.2, 100, "calm")[0] == "sell"         # obojí → prodej (ztráta)


def test_taxable_gain_under_3_years_is_held_unless_hard_break():
    assert tf.sell_decision(-9, "PŘEPÁLENÁ", 0.3, 400, "calm")[0] == "hold_tax"
    assert tf.sell_decision(-9, "PŘEPÁLENÁ", 0.3, 3 * 365 + 5, "calm")[0] == "sell"   # časový test splněn
    assert tf.sell_decision(-40, "PŘEPÁLENÁ", 0.3, 400, "calm")[0] == "sell"          # tvrdý obrat


def test_never_sell_in_panic_and_only_hard_in_tension():
    assert tf.sell_decision(-40, "PŘEPÁLENÁ", -0.3, 2000, "panic")[0] == "hold_regime"
    assert tf.sell_decision(-9, "PŘEPÁLENÁ", -0.3, 2000, "tension")[0] == "hold_regime"
    assert tf.sell_decision(-40, "PŘEPÁLENÁ", -0.3, 2000, "tension")[0] == "sell"


def test_falling_knife():
    falling = [100] * 14 + [98, 96, 94, 92, 90, 88]          # −12 % za 5 dní
    assert tf.falling_knife(falling, 8.0)[0] is True
    assert tf.falling_knife([100] * 20, 8.0) == (False, 0.0)
    assert tf.falling_knife(falling, 0)[0] is False          # panika: práh 0 se nevyhodnocuje
    assert tf.falling_knife([100, 99], 8.0) == (False, None)  # málo dat
    mild = [100] * 14 + [100, 99, 98, 97, 96, 95]            # −5 % a nové minimum
    assert tf.falling_knife(mild, 8.0)[0] is True            # ≥ polovina prahu + nové minimum
    assert tf.falling_knife(mild, 4.0)[0] is True


def test_policy_table():
    assert tf.REGIME_POLICY["panic"]["max_buys"] == 0
    assert tf.REGIME_POLICY["tension"]["min_score"] > tf.REGIME_POLICY["calm"]["min_score"]
    assert tf.REGIME_POLICY["recovering"]["size"] == 0.5


def test_note_explains_waiting_and_tax():
    ctx = {"state": "panic", "label": "Panika", "reasons": ["VIX 33 je nad 30"], "known": True,
           "waiting": ["AAA (−9 % za 5 dní)"], "watch": ["BBB (konvikce 40)"],
           "tax_holds": ["CCC (zisk +30 %)"], "sell_deferred": []}
    n = tf._build_note([], 1_000_000, 1_000_000, ctx)
    for part in ("Panika", "nenakupuje", "neprodává", "AAA", "BBB", "CCC", "kvůli dani"):
        assert part in n, part


# ── celý běh run() s napodobenými daty ───────────────────────────────────────
def _sig(*items):
    return {"valuation": [{"ticker": t, "name": t, "verdict": v, "composite": c} for t, v, c in items]}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(tf, "TOKEN", "x")
    monkeypatch.setattr(tf, "DB_PATH", str(tmp_path / "f.db"))
    monkeypatch.setattr(tf, "gspc_history", lambda: [])
    monkeypatch.setattr(tf, "time", type("T", (), {"sleep": staticmethod(lambda s: None),
                                                    "strftime": staticmethod(lambda *a: ""),
                                                    "gmtime": staticmethod(lambda *a: None)}))
    state = {"sig": _sig(("AAA", "LEVNÁ", 80), ("BBB", "LEVNÁ", 75)), "regime": "calm",
             "price": {"AAA": 100.0, "BBB": 100.0}, "closes": [100.0] * 25}
    monkeypatch.setattr(tf, "fetch_signals", lambda: state["sig"])
    monkeypatch.setattr(tf, "yahoo_price", lambda s: (state["price"].get(s, 100.0), "CZK"))
    monkeypatch.setattr(tf, "daily_closes", lambda s: state["closes"])
    labels = {"calm": "Klid", "recovering": "Stabilizace", "tension": "Napětí", "panic": "Panika"}
    monkeypatch.setattr(risk_regime, "get_regime",
                        lambda: {"state": state["regime"], "label": labels[state["regime"]], "reasons": ["test"]})

    def trades():
        con = sqlite3.connect(tf.DB_PATH)
        rows = con.execute("SELECT action,symbol,value_czk FROM trades ORDER BY id").fetchall()
        con.close()
        return rows

    def add_position(sym, avg, opened, conv=30):
        con = tf.db()
        con.execute("INSERT INTO positions(symbol,name,qty,avg_cost,currency,opened_at,conviction) VALUES(?,?,?,?,?,?,?)",
                    (sym, sym, 100.0, avg, "CZK", opened, conv))
        con.commit(); con.close()

    return state, trades, add_position


def test_calm_buys_normally(env):
    state, trades, _ = env
    tf.run(False, False)
    assert [t[0] for t in trades()] == ["buy", "buy"]


def test_panic_buys_nothing_and_sells_nothing(env):
    state, trades, add = env
    state["regime"] = "panic"
    add("OLD", 100.0, "2020-01-01", conv=-50)                 # tvrdý obrat, ale panika
    state["sig"] = _sig(("AAA", "LEVNÁ", 80), ("OLD", "PŘEPÁLENÁ", 10))
    tf.run(False, False)
    assert trades() == []                                      # ani nákup, ani prodej


def test_tension_only_strong_and_half_size(env):
    state, trades, _ = env
    state["regime"] = "tension"
    # MID (konvikce ≈ 28) projde běžným prahem 22, ale ne prahem napětí 34 → jen AAA (≈ 35)
    state["sig"] = _sig(("AAA", "LEVNÁ", 80), ("MID", "LEVNÁ", 60))
    tf.run(False, False)
    t = trades()
    assert [x[:2] for x in t] == [("buy", "AAA")]              # jen nejsilnější, max 1 nákup
    calm_target = 0.03 + (35 - tf.BUY_TH) / 38 * (tf.MAX_WEIGHT - 0.03)   # konvikce ≈ 35
    assert t[0][2] < 0.6 * calm_target * 1_000_000             # zhruba polovina cílové váhy


def test_momentum_without_valuation_is_not_bought(env):
    """3+ roky: čisté momentum (bez valuace) nebo drahá akcie se nekupuje, ani když má vysoké skóre."""
    state, trades, _ = env
    state["sig"] = {
        "valuation": [{"ticker": "EXP", "name": "EXP", "verdict": "NAPJATÁ", "composite": 95}],
        "discovery": [{"ticker": "MOM", "score": 100, "ret_20d": 40, "rel_vol": 2, "news_7d": 5},
                      {"ticker": "EXP", "score": 100, "ret_20d": 40, "rel_vol": 2, "news_7d": 5}],
    }
    assert tf.score_candidates(state["sig"])["MOM"]["score"] > tf.BUY_TH   # skóre by stačilo…
    tf.run(False, False)
    assert trades() == []                                                   # …ale bez valuace/drahé = ne


def test_falling_knife_waits_even_if_cheap(env):
    state, trades, _ = env
    state["regime"] = "tension"
    state["closes"] = [100.0] * 14 + [98, 96, 94, 92, 90, 88]
    tf.run(False, False)
    assert trades() == []                                      # levná, ale ještě padá → čeká


def test_exceptional_sell_taxed_vs_free(env):
    state, trades, add = env
    state["sig"] = _sig(("TAX", "PŘEPÁLENÁ", 60), ("FREE", "PŘEPÁLENÁ", 60))
    state["price"].update({"TAX": 130.0, "FREE": 130.0})
    add("TAX", 100.0, (date.today() - timedelta(days=200)).isoformat())     # zisk, <3 roky → drží
    add("FREE", 100.0, (date.today() - timedelta(days=4 * 365)).isoformat())  # >3 roky → prodá
    tf.run(False, False)
    t = trades()
    assert ("sell", "FREE") in [x[:2] for x in t]
    assert "TAX" not in [x[1] for x in t]


def test_no_routine_profit_taking(env):
    """Dřív fond ořezával 40 % při zisku >40 % a napjaté valuaci — teď ne (daň)."""
    state, trades, add = env
    state["sig"] = _sig(("WIN", "NAPJATÁ", 50))
    state["price"]["WIN"] = 200.0
    add("WIN", 100.0, (date.today() - timedelta(days=300)).isoformat())
    tf.run(False, False)
    assert all(x[1] != "WIN" for x in trades())
