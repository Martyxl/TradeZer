"""Klasifikace režimu trhu (data/risk_regime.py) — prahy, stabilizace po šoku, geopolitika."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "data"))
from risk_regime import classify, compute_indicators  # noqa: E402

CALM = {"vix": 14.0, "vix_chg_1d": 0.5, "vix_chg_5d": 2.0, "vix_peak10": 15.0, "vix_recovery": 0.07,
        "spx_chg_1d": 0.3, "spx_chg_5d": 1.0, "spx_dd_20d": -0.5, "spx_dd_10d": -0.3,
        "spx_above_5d_low": True, "oil_chg_5d": 1.0, "gold_chg_5d": 0.5}


def mk(**kw):
    return {**CALM, **kw}


def test_calm():
    r = classify(CALM)
    assert r["state"] == "calm" and r["label"] == "Klid"


def test_panic_by_vix_or_daily_drop_or_drawdown():
    assert classify(mk(vix=33, vix_peak10=33, vix_recovery=0))["state"] == "panic"
    assert classify(mk(spx_chg_1d=-3.4))["state"] == "panic"
    assert classify(mk(spx_dd_20d=-9))["state"] == "panic"


def test_tension_by_vix_oil_gold():
    assert classify(mk(vix=24, vix_peak10=24, vix_recovery=0))["state"] == "tension"
    assert classify(mk(oil_chg_5d=12))["state"] == "tension"
    assert classify(mk(gold_chg_5d=5, vix=19, vix_peak10=19, vix_recovery=0))["state"] == "tension"
    # zlato roste, ale VIX klidný → nic (nejde o útěk do bezpečí)
    assert classify(mk(gold_chg_5d=5))["state"] == "calm"


def test_recovering_after_shock_when_stabilized():
    # VIX byl 36, teď 26 (−28 % od vrcholu), S&P netvoří nová minima → stabilizace
    r = classify(mk(vix=26, vix_peak10=36, vix_recovery=0.28, spx_dd_10d=-7, spx_dd_20d=-6,
                    spx_above_5d_low=True))
    assert r["state"] == "recovering" and "stabilizuje" in r["reasons"][0]


def test_shock_without_stabilization_stays_tension():
    # S&P −7 % od maxima, VIX už klidný, ale trh dál tvoří nová minima → ještě ne
    r = classify(mk(vix=19, vix_peak10=20, vix_recovery=0.05, spx_dd_10d=-7, spx_above_5d_low=False))
    assert r["state"] == "tension" and "bez potvrzené stabilizace" in r["reasons"][0]


def test_panic_is_not_downgraded_to_recovering():
    r = classify(mk(vix=31, vix_peak10=40, vix_recovery=0.22, spx_dd_10d=-9, spx_above_5d_low=True))
    assert r["state"] == "panic"


def test_geopolitics_alone_never_causes_panic():
    assert classify(CALM, geo_sev=1)["state"] == "calm"
    assert classify(CALM, geo_sev=2)["state"] == "tension"
    r = classify(CALM, geo_sev=3)  # jaderná hrozba, ale trh klidný → napětí, ne panika
    assert r["state"] == "tension" and any("geopolitika" in x for x in r["reasons"])
    # s potvrzením trhem (VIX 25) → panika
    assert classify(mk(vix=25, vix_peak10=25, vix_recovery=0), geo_sev=3)["state"] == "panic"


def test_missing_data_does_not_crash():
    assert classify({})["state"] == "calm"


def test_compute_indicators_from_series():
    vix = [15] * 8 + [38, 35, 30, 27, 24, 22, 21]
    spx = [100] * 10 + [96, 93, 94, 95, 96]
    ind = compute_indicators({"vix": vix, "spx": spx})
    assert ind["vix"] == 21 and ind["vix_peak10"] == 38 and ind["vix_recovery"] > 0.4
    assert ind["spx_dd_10d"] <= -4 and ind["spx_above_5d_low"] is True


def test_parse_geo_rejects_truncated_response():
    from risk_regime import _parse_geo
    ok = '{"severity": 1, "summary": "Klid.", "headlines": [{"i": 0, "severity": 1, "why": "x"}]}'
    assert _parse_geo(ok)["severity"] == 1
    assert _parse_geo("```json\n" + ok + "\n```")["severity"] == 1
    # useknuto uprostřed → NESMÍ vrátit vnořený objekt titulku jako celek
    cut = '{"severity": 2, "summary": "Útok.", "headlines": [{"i": 16, "severity": 2, "why": "x"}, {"i": 6, "sev'
    assert _parse_geo(cut) is None
    assert _parse_geo('{"i": 16, "severity": 2, "why": "x"}') is None  # chybí summary


def _series(n=400, crash=False):
    """Syntetické zarovnané denní řady; crash = posledních 15 dní výprodej + skok VIX."""
    from datetime import date, timedelta
    d0 = date(2025, 1, 1)
    days = [(d0 + timedelta(days=i)).isoformat() for i in range(n)]
    out = {k: {} for k in ("spx", "vix", "vix3m", "tlt", "hyg", "ief")}
    for i, d in enumerate(days):
        hit = crash and i >= n - 15
        k = i - (n - 15)
        out["spx"][d] = 100 + i * 0.05 - (k * 1.2 if hit else 0)
        out["vix"][d] = 15 + (i % 7) * 0.3 + (k * 1.5 if hit else 0)
        out["vix3m"][d] = 17 + (i % 5) * 0.2 + (k * 0.6 if hit else 0)
        out["tlt"][d] = 90 + (i % 11) * 0.1 + (k * 0.3 if hit else 0)
        out["hyg"][d] = 75 + i * 0.01 - (k * 0.4 if hit else 0)
        out["ief"][d] = 95 + (i % 9) * 0.05
    return out


def test_sentiment_extreme_fear_after_selloff():
    from risk_regime import sentiment_from_series
    s = sentiment_from_series(_series(crash=True))
    assert s["band"] == "extreme_fear" and s["score"] < 20 and s["backwardation"] is True
    assert {p["key"] for p in s["parts"]} == {"vix50", "term", "mom", "haven", "junk"}
    assert s["history"]["next_day_move"] > 1


def test_sentiment_needs_enough_history():
    from risk_regime import sentiment_from_series
    assert sentiment_from_series(_series(n=200)) is None
    calm = sentiment_from_series(_series())
    assert calm is not None and calm["band"] != "extreme_fear" and calm["backwardation"] is False


def test_history_from_series_and_weekly_cache(tmp_path, monkeypatch):
    import json, time
    import risk_regime as rr
    s = _series(n=1600, crash=True)
    ndx = {d: v * 1.5 for d, v in s["spx"].items()}
    hist = rr.history_from_series(s, ndx)
    # syntetika nemá všechna pásma ≥ 30 dní → None (pak se drží záloha); s reálnými daty test níž
    assert hist is None or {"all", "extreme_fear", "neutral", "period"} <= set(hist)
    cache = tmp_path / "h.json"
    monkeypatch.setattr(rr, "HIST_CACHE", str(cache))
    fresh = {"all": {"up": 50}, "extreme_fear": {"up": 1}, "period": "x"}
    cache.write_text(json.dumps({"computed_at": time.time(), "history": fresh}), encoding="utf-8")
    assert rr.load_history() == fresh                                  # čerstvá cache → bez stahování
    cache.write_text(json.dumps({"computed_at": time.time() - 8 * 86400, "history": fresh}), encoding="utf-8")
    monkeypatch.setattr(rr, "yahoo_daily", lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    assert rr.load_history() == fresh                                  # přepočet selhal → stará cache
