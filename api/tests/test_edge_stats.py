"""Edge statistiky (data/edge_stats.py) a ET časy v data/compute_stats.py — syntetické bary se známým výsledkem."""
import os
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "data"))
import edge_stats as es  # noqa: E402

ET = "America/New_York"


def bars_from(rows):
    """rows = [(ET datetime naive, o, h, l, c)] → DataFrame s UTC ts."""
    ts = pd.to_datetime([r[0] for r in rows]).tz_localize(ET).tz_convert("UTC")
    return pd.DataFrame({"ts": ts, "open": [r[1] for r in rows], "high": [r[2] for r in rows],
                         "low": [r[3] for r in rows], "close": [r[4] for r in rows]})


def rth_path(d: date, closes, o=100.0, start=(9, 30), n=78, wick=0.0):
    """RTH bary dne d: close podle `closes` (délka n), high/low = max/min(open, close) ± wick."""
    rows, prev = [], o
    t0 = datetime(d.year, d.month, d.day, *start)
    for i in range(n):
        c = closes[i]
        rows.append((t0 + timedelta(minutes=5 * i), prev, max(prev, c) + wick, min(prev, c) - wick, c))
        prev = c
    return rows


def weekdays(start: date, k: int):
    out, d = [], start
    while len(out) < k:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


# ------------------------------------------------------------ statistika

def test_wilson_and_coin_flag():
    assert es.wilson(50, 100) == [40.4, 59.6]
    p = es.prop(60, 100)
    assert p["pct"] == 60.0 and p["coin"] is False is (p["ci"][0] <= 50)
    assert es.prop(54, 100)["coin"] is True
    assert es.prop(0, 0)["pct"] is None


def test_percentile_of_interpolates():
    grid = [i / 20 for i in range(21)]          # rovnoměrné 0..1 → hodnota = percentil
    assert es.percentile_of(0.5, grid) == 50.0
    assert es.percentile_of(0.525, grid) == 52.5
    assert es.percentile_of(-1, grid) == 0.0 and es.percentile_of(5, grid) == 100.0


# ------------------------------------------------------------ ET / letní čas

def test_rth_open_follows_dst():
    """9:30 ET = 14:30 UTC v zimě, 13:30 UTC v létě — obojí musí být minuta 570."""
    df = pd.DataFrame({"ts": pd.to_datetime(["2026-01-15 14:30", "2026-07-15 13:30"], utc=True),
                       "open": [1, 1], "high": [1, 1], "low": [1, 1], "close": [1, 1]})
    assert list(es.prep(df)["et_min"]) == [570, 570]


def test_compute_stats_load_m5_uses_et(tmp_path, monkeypatch):
    import compute_stats as cs
    ts = [int(pd.Timestamp(x, tz="UTC").timestamp() * 1000) for x in
          ("2026-01-15 14:30", "2026-07-15 13:30", "2026-07-15 13:31")]   # poslední = živý bar mimo mřížku
    pd.DataFrame({"timestamp": ts, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 1}).to_csv(
        tmp_path / "x-m5-test.csv", index=False)
    monkeypatch.setattr(cs, "RAW", tmp_path)
    df = cs.load_m5("x-m5-*.csv")
    assert list(df["hour_f"]) == [9.5, 9.5]
    assert [str(d) for d in df["tday"]] == ["2026-01-15", "2026-07-15"]


def test_trading_day_starts_18_et():
    df = pd.DataFrame({"ts": pd.to_datetime(["2026-03-02 22:59", "2026-03-02 23:00"], utc=True),  # 17:59 / 18:00 EST
                       "open": 1, "high": 1, "low": 1, "close": 1})
    assert [str(d) for d in es.prep(df)["tday"]] == ["2026-03-02", "2026-03-03"]


# ------------------------------------------------------------ RTH dny

def test_trend_day_metrics_on_straight_up_day():
    d = date(2026, 3, 2)
    closes = [100 + 0.1 * (i + 1) for i in range(78)]
    r = es.rth_days(bars_from(rth_path(d, closes)), (9.5, 16.0), "t")[d]
    assert r["der"] == pytest.approx(1.0)
    assert r["cl"] == pytest.approx(1.0)
    assert r["retr"] == pytest.approx(0.0)
    assert r["trend"] == "bull"
    assert r["t_low"] == 0 and r["t_high"] == 385
    assert r["range"] == pytest.approx(7.8)
    cp = r["cp"][60]
    assert cp["new_high"] and not cp["new_low"] and cp["cont"] is True


def test_choppy_day_is_not_trend_and_incomplete_day_dropped():
    d1, d2 = date(2026, 3, 2), date(2026, 3, 3)
    chop = [100 + (1 if i % 2 else -1) for i in range(78)]
    rows = rth_path(d1, chop) + rth_path(d2, [100.0] * 40, n=40)   # zkrácený den (40 barů) se zahodí
    days = es.rth_days(bars_from(rows), (9.5, 16.0), "t")
    assert list(days) == [d1]
    assert days[d1]["trend"] is None and days[d1]["der"] < 0.05


def test_checkpoint_uses_only_closed_bars():
    d = date(2026, 3, 2)
    closes = [100.0] * 6 + [110.0] + [100.0] * 71       # skok v baru 10:00–10:05 (start = 30 min)
    r = es.rth_days(bars_from(rth_path(d, closes)), (9.5, 16.0), "t")[d]
    assert r["cp"][30]["so_far"] == pytest.approx(0.0)  # bar začínající v 30. minutě ještě není uzavřený
    assert r["cp"][30]["new_high"] is True


def test_typical_is_median_of_previous_days_only():
    ds = weekdays(date(2026, 1, 5), 25)
    rows = []
    for i, d in enumerate(ds):
        rows += rth_path(d, [100 + 0.01 * (i + 1) * (k + 1) for k in range(78)])   # každý den větší rozsah
    days = es.merge_days(es.rth_days(bars_from(rows), (9.5, 16.0), "t"))
    es.add_typical(days)
    assert days[9][1]["typ_range"] is None            # < 10 předchozích dní
    assert days[10][1]["typ_range"] == pytest.approx(float(np.median([r["range"] for _, r in days[0:10]])))
    # den 24: medián dní 4–23 (posledních 20), dnešek se nezapočítává
    assert days[24][1]["typ_range"] == pytest.approx(float(np.median([r["range"] for _, r in days[4:24]])))
    assert days[24][1]["typ_range"] < days[24][1]["range"]


def test_merge_prefers_first_source():
    d = date(2026, 3, 2)
    a = {d: {"src": "twelvedata"}}
    b = {d: {"src": "own"}, date(2026, 3, 3): {"src": "own"}}
    m = es.merge_days(a, b)
    assert [r["src"] for _, r in m] == ["twelvedata", "own"]


# ------------------------------------------------------------ bloky nad více dny

def _many_days(k=60, seed=1):
    rng = np.random.default_rng(seed)
    rows = []
    for d in weekdays(date(2025, 1, 6), k):
        steps = rng.normal(0, 0.1, 78)
        rows += rth_path(d, list(100 + np.cumsum(steps)), wick=0.02)
    return rows


def test_blocks_are_consistent():
    bars = bars_from(_many_days())
    ev = {"cpi": {date(2025, 2, 12), date(2025, 3, 12)}}
    edge = es.compute_edge([("t", bars)], [], (9.5, 16.0), ev, ref_price=20000.0)
    assert edge["meta"]["days"] == 60 and edge["meta"]["sources"] == {"t": 60}
    ex = edge["extremes"]
    f = ex["first60"]
    assert f["either"]["k"] == f["high"]["k"] + f["low"]["k"] - f["both"]["k"]
    assert sum(s["high"]["k"] for s in ex["slots"]) == ex["n"]
    # čím později, tím častěji už high stojí
    hd = [ex["checkpoints"][str(c)]["high_done"]["pct"] for c in (30, 120, 300)]
    assert hd == sorted(hd)
    rb = edge["range"]["checkpoints"]["60"]
    assert len(rb["so_far_q"]) == 21 and rb["so_far_q"] == sorted(rb["so_far_q"])
    assert sum(b["ext"]["n"] for b in rb["buckets"]) == rb["n"]
    tr = edge["trend"]
    assert tr["der_random_walk"] == pytest.approx(1 / np.sqrt(78), abs=1e-3)
    assert sum(v["k"] for v in tr["close_location"].values()) == tr["n"]
    # makro: jen dny s typickým dnem (od 11. dne); CPI dny 2025-02-12 a 03-12 už ho mají
    assert edge["macro"]["cpi"]["n"] == 2 and edge["macro"]["none"]["n"] == 60 - 10 - 2


def test_macro_ratio_detects_wild_event_day():
    rows = []
    ds = weekdays(date(2025, 1, 6), 40)
    for i, d in enumerate(ds):
        amp = 0.6 if i in (30, 35) else 0.2           # dva „FOMC“ dny s 3× větším rozsahem
        rows += rth_path(d, [100 + amp * np.sin(k / 6) for k in range(78)])
    edge = es.compute_edge([("t", bars_from(rows))], [], (9.5, 16.0), {"fomc": {ds[30], ds[35]}}, None)
    m = edge["macro"]
    assert m["fomc"]["n"] == 2
    assert m["fomc"]["rth"]["p50"] == pytest.approx(3.0, rel=0.05)
    assert m["none"]["rth"]["p50"] == pytest.approx(1.0, rel=0.05)


# ------------------------------------------------------------ sessions

def _session_day(td: date, pre_up=True, ny_low_first=True):
    """Asia 20–24 (předchozí den) range 99–101; Pre-London nad 101 (nebo uvnitř), London 102,5 high;
    NY nejdřív pod London low, pak nad London high."""
    prev = td - timedelta(days=1)
    rows = []
    t = datetime(prev.year, prev.month, prev.day, 20, 0)
    for i in range(48):
        c = 101 if i == 10 else 99 if i == 20 else 100
        rows.append((t + timedelta(minutes=5 * i), 100, max(100, c), min(100, c), 100))
    t = datetime(td.year, td.month, td.day, 0, 0)
    for i in range(24):
        h = 101.5 if pre_up else 100.5
        rows.append((t + timedelta(minutes=5 * i), 100.2, h, 100.0, 100.2))
    t = datetime(td.year, td.month, td.day, 2, 0)
    for i in range(36):
        rows.append((t + timedelta(minutes=5 * i), 101, 102.5 if i == 5 else 101.2, 100.5, 101))
    t = datetime(td.year, td.month, td.day, 8, 0)
    for i in range(96):
        lo = 100.0 if (ny_low_first and i == 10) else 100.8
        hi = 103.0 if i == 60 else 101.5
        rows.append((t + timedelta(minutes=5 * i), 101, hi, lo, 101))
    return rows


def test_session_day_classification():
    td = date(2026, 3, 3)
    r = es.session_days(bars_from(_session_day(td)), "own")[td]
    assert r["pre_high"] and not r["pre_low"]
    assert r["london_high"] and not r["london_low"] and r["scenario"] == "high_only"
    assert r["london_ext_high"]                       # London 102,5 > Pre-London 101,5
    assert r["ny_lh"] and r["ny_ll"] and r["ny_first"] == "low"


def test_sessions_block_conditionals():
    rows = []
    ds = weekdays(date(2026, 1, 6), 40)
    for i, d in enumerate(ds):
        rows += _session_day(d, pre_up=i % 2 == 0, ny_low_first=i % 4 < 2)
    sb = es.sessions_block(es.merge_days(es.session_days(bars_from(rows), "own")))
    assert sb["n"] == 40
    assert sb["ny_by_scenario"]["high_only"]["n"] == 40
    assert sb["high_only_low_first"]["n"] == 20 and sb["high_only_low_first"]["pct"] == 100.0
    assert sb["pre_london"]["pre_high"]["k"] == 20


# ------------------------------------------------------------ živý stav

def test_live_state_midday():
    hist = bars_from(_many_days(80))
    edge = es.compute_edge([("t", hist)], [], (9.5, 16.0), {"cpi": {date(2026, 3, 4)}}, 20000.0)
    d = date(2026, 3, 4)                               # středa, EST
    rows = rth_path(d, [100 + 0.05 * (i + 1) for i in range(78)])
    now = datetime(2026, 3, 4, 17, 2, tzinfo=timezone.utc)   # 12:02 ET → checkpoint 120
    st = es.live_state(bars_from(rows), edge, now, ["cpi"], price_scale=20000.0)
    assert st["phase"] == "rth" and st["now_et"] == "12:02"
    rr = st["range"]
    assert rr["checkpoint"] == 120
    assert rr["so_far_pct"] == pytest.approx((100 + 0.05 * 30 - 100) / 100 * 100, rel=1e-6)  # 30 uzavřených barů
    assert rr["remaining_pts"]["p50"] <= rr["remaining_pts"]["p90"]
    assert 0 <= rr["percentile"] <= 100
    # 30 uzavřených barů → konec 150. minuty; low z 1. baru stojí 150 min, high z posledního 5 min
    assert st["extremes"]["lo_age"] == 150 and st["extremes"]["hi_age"] == 5
    assert st["extremes"]["low_holds"]["n"] > 0
    import json
    json.dumps(st, allow_nan=False)
    assert st["trend"]["direction"] == "up" and st["trend"]["der"] == pytest.approx(1.0)
    assert st["macro"][0]["event"] == "cpi"


def test_live_state_after_close_reports_final_category():
    hist = bars_from(_many_days(80))
    edge = es.compute_edge([("t", hist)], [], (9.5, 16.0), {}, 20000.0)
    d = date(2026, 3, 4)
    rows = rth_path(d, [100 + 0.05 * (i + 1) for i in range(78)])   # 3,9 % → daleko nad typickým dnem
    st = es.live_state(bars_from(rows), edge, datetime(2026, 3, 4, 21, 30, tzinfo=timezone.utc), [])
    assert st["phase"] == "post"
    assert st["range"]["category"] == "extreme" and st["range"]["final_percentile"] == 100.0
    assert "remaining_pts" not in st["range"]


def test_live_state_premarket_has_no_range():
    edge = es.compute_edge([("t", bars_from(_many_days(40)))], [], (9.5, 16.0), {}, None)
    st = es.live_state(bars_from([(datetime(2026, 3, 4, 8, 0), 100, 101, 99, 100)]), edge,
                       datetime(2026, 3, 4, 13, 10, tzinfo=timezone.utc), [])
    assert st["phase"] == "pre" and "range" not in st
