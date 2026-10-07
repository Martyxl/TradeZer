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
