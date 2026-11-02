"""Statistiky „Edge“ (inspirace: NQ Statistical Edge) — měřené na našich datech, ne přebírané.

Bloky (všechny pravděpodobnosti s počtem pozorování a 95% Wilsonovým intervalem):
  range     — rozsah RTH jako rozdělení (percentily) + ZBÝVAJÍCÍ rozsah od checkpointu
              (varianta „rozšíření“: konečný range − range do checkpointu; jen data známá v čase)
  extremes  — kdy vzniká high/low RTH (prvních 30/60 min, 30min sloty) + šance, že už stojí
  sessions  — Asia → Pre-London → London → NY scénáře (proražení a jejich podmíněné frekvence)
  trend     — objektivní trendový den: DER, Close Location, max. retracement; směr prvních 30 min
  macro     — rozsah dne / okna kolem CPI, NFP, PPI, FOMC vůči typickému dni

Normalizace: rozsahy v % ceny a dělené „typickým dnem“ = medián předchozích 20 seancí (bez
pohledu do budoucnosti). Proto jdou spojit roky 2020–2026 i zdroje s jinou cenou (QQQ vs. NQ):
body se dopočítají až z aktuální ceny instrumentu.

Časy v America/New_York (ET), včetně přechodů letního času.
Čisté funkce nad DataFrame (ts UTC, open, high, low, close) → testovatelné bez sítě.
"""
from __future__ import annotations

import math
from datetime import date, datetime

import numpy as np
import pandas as pd

TZ = "America/New_York"
CHECKPOINTS = [30, 60, 90, 120, 180, 240, 300]     # minuty od RTH open
TYPICAL_N, TYPICAL_MIN = 20, 10
TREND_DER, TREND_CL, TREND_RETR = 0.5, 0.8, 0.5    # pracovní definice trendového dne (dokument, kap. 4)
QS = [round(x * 0.05, 2) for x in range(21)]       # 0 %, 5 %, … 100 % — pro percentil dnešního dne
SESSION_WINDOWS = {"asia": (20.0, 24.0), "pre": (0.0, 2.0), "london": (2.0, 5.0), "ny": (8.0, 16.0)}


# ---------------------------------------------------------------- statistika

def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    if n <= 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h) * 100, 1), round(min(1.0, c + h) * 100, 1)]


def prop(k: int, n: int) -> dict:
    """Frekvence s intervalem. coin=True → interval obsahuje 50 % (neodlišitelné od hodu mincí)."""
    ci = wilson(k, n)
    return {"pct": round(100 * k / n, 1) if n else None, "k": int(k), "n": int(n), "ci": ci,
            "coin": bool(ci and ci[0] <= 50 <= ci[1])}


def quant(vals, qs=(0.25, 0.5, 0.75, 0.9), nd=3) -> dict:
    a = np.asarray([v for v in vals if v is not None and np.isfinite(v)], dtype=float)
    if not len(a):
        return {"n": 0}
    return {"n": int(len(a)), **{f"p{int(q * 100)}": round(float(np.quantile(a, q)), nd) for q in qs}}


def boot_median_ci(vals, n_boot: int = 1000, seed: int = 0) -> list[float] | None:
    a = np.asarray(vals, dtype=float)
    if len(a) < 5:
        return None
    rng = np.random.default_rng(seed)
    meds = np.median(rng.choice(a, size=(n_boot, len(a)), replace=True), axis=1)
    return [round(float(np.quantile(meds, 0.025)), 3), round(float(np.quantile(meds, 0.975)), 3)]


def percentile_of(value: float, qgrid: list[float]) -> float | None:
    """Kolikátý percentil je `value` v rozdělení zadaném kvantily QS (lineární interpolace)."""
    if value is None or not qgrid:
        return None
    if value <= qgrid[0]:
        return 0.0
    if value >= qgrid[-1]:
        return 100.0
    for i in range(1, len(qgrid)):
        if value <= qgrid[i]:
            lo, hi = qgrid[i - 1], qgrid[i]
            f = 0 if hi == lo else (value - lo) / (hi - lo)
            return round((QS[i - 1] + f * (QS[i] - QS[i - 1])) * 100, 1)
    return 100.0


# ---------------------------------------------------------------- příprava barů

def prep(df: pd.DataFrame) -> pd.DataFrame:
    """Přidá ET čas: et_date, et_min (minuta dne), tday (obchodní den od 18:00 ET), hour_et."""
    d = df[["ts", "open", "high", "low", "close"]].copy()
    if d["ts"].dt.tz is None:
        d["ts"] = d["ts"].dt.tz_localize("UTC")
    d = d.sort_values("ts").drop_duplicates("ts").reset_index(drop=True)
    et = d["ts"].dt.tz_convert(TZ)
    d["et_date"] = et.dt.date
    d["et_min"] = et.dt.hour * 60 + et.dt.minute
    d["hour_et"] = d["et_min"] / 60.0
    d["tday"] = (et + pd.Timedelta(hours=6)).dt.date
    return d


def load_csv(path) -> pd.DataFrame:
    p = pd.read_csv(path)
    p = p[p["timestamp"] % 300000 == 0]          # jen uzavřené 5min bary
    p["ts"] = pd.to_datetime(p["timestamp"], unit="ms", utc=True)
    return p


# ---------------------------------------------------------------- RTH dny

def _rth_record(day: pd.DataFrame, open_min: int, length: int) -> dict | None:
    bars = day[(day["et_min"] >= open_min) & (day["et_min"] < open_min + length)]
    expected = length // 5
    if len(bars) < 0.9 * expected:
        return None                                # svátek / zkrácený den / díra v datech
    t = (bars["et_min"].to_numpy() - open_min).astype(int)
    o = float(bars["open"].iloc[0])
    h_arr, l_arr, c_arr = bars["high"].to_numpy(float), bars["low"].to_numpy(float), bars["close"].to_numpy(float)
    H, L, C = float(h_arr.max()), float(l_arr.min()), float(c_arr[-1])
    if o <= 0 or H <= L:
        return None
    path = np.concatenate([[o], c_arr])
    steps = np.abs(np.diff(path))
    rec = {
        "o": o, "h": H, "l": L, "c": C,
        "range": (H - L) / o * 100,
        "t_high": int(t[int(np.argmax(h_arr))]), "t_low": int(t[int(np.argmin(l_arr))]),
        "der": float(abs(C - o) / steps.sum()) if steps.sum() > 0 else 0.0,
        "cl": float((C - L) / (H - L)),
        "n_steps": int(len(steps)),
    }
    # max. retracement proti směru dne jako podíl denního rozsahu (impuls = od open k běžícímu extrému)
    prev_hi = np.maximum.accumulate(np.concatenate([[o], h_arr[:-1]]))
    prev_lo = np.minimum.accumulate(np.concatenate([[o], l_arr[:-1]]))
    r_up = float(np.clip(prev_hi - l_arr, 0, None).max() / (H - L))
    r_dn = float(np.clip(h_arr - prev_lo, 0, None).max() / (H - L))
    rec["retr"] = r_up if C > o else r_dn if C < o else min(r_up, r_dn)
    if C > o and rec["der"] >= TREND_DER and rec["cl"] >= TREND_CL and rec["retr"] <= TREND_RETR:
        rec["trend"] = "bull"
    elif C < o and rec["der"] >= TREND_DER and rec["cl"] <= 1 - TREND_CL and rec["retr"] <= TREND_RETR:
        rec["trend"] = "bear"
    else:
        rec["trend"] = None
    # checkpointy: jen bary UZAVŘENÉ do času c (start < c)
    cps = {}
    for c in CHECKPOINTS:
        if c >= length:
            continue
        m = t < c
        if not m.any():
            continue
        hc, lc = h_arr[m], l_arr[m]
        hi_c, lo_c = float(hc.max()), float(lc.min())
        pc = float(c_arr[m][-1])
        st = steps[: int(m.sum())]
        cps[c] = {
            "so_far": (hi_c - lo_c) / o * 100,
            "new_high": bool(H > hi_c), "new_low": bool(L < lo_c),
            "hi_age": c - int(t[m][int(np.argmax(hc))]), "lo_age": c - int(t[m][int(np.argmin(lc))]),
            "der": float(abs(pc - o) / st.sum()) if st.sum() > 0 else 0.0,
            "move": pc - o, "cont": bool((C - pc) * np.sign(pc - o) > 0) if pc != o else None,
            "p": pc,
        }
    rec["cp"] = cps
    f30 = bars[t < 30]
    rec["first30"] = (float(f30["high"].max()) - float(f30["low"].min())) / o * 100 if len(f30) else None
    a14 = bars[bars["et_min"] >= 14 * 60]
    rec["after14"] = (float(a14["high"].max()) - float(a14["low"].min())) / o * 100 if len(a14) >= 6 else None
    return rec


def rth_days(bars: pd.DataFrame, rth: tuple[float, float], src: str) -> dict[date, dict]:
    """{datum ET: záznam dne} pro všechny kompletní RTH seance v barech."""
    b = bars if "et_min" in bars else prep(bars)
    open_min, length = int(round(rth[0] * 60)), int(round((rth[1] - rth[0]) * 60))
    out = {}
    for d, day in b.groupby("et_date"):
        if pd.Timestamp(d).weekday() > 4:
            continue
        r = _rth_record(day, open_min, length)
        if r:
            r["src"] = src
            out[d] = r
    return out


def merge_days(*sources: dict[date, dict]) -> list[tuple[date, dict]]:
    """Spojí dny ze zdrojů; dřívější zdroj má přednost (placený → vlastní záloha)."""
    out: dict[date, dict] = {}
    for s in sources:
        for d, r in s.items():
            out.setdefault(d, r)
    return sorted(out.items())


def add_typical(days: list[tuple[date, dict]], fields=("range", "first30", "after14")) -> None:
    """Typický den = medián předchozích 20 seancí (jen minulost). Uloží r['typ_<field>']."""
    for f in fields:
        hist: list[float] = []
        for _, r in days:
            r[f"typ_{f}"] = float(np.median(hist[-TYPICAL_N:])) if len(hist) >= TYPICAL_MIN else None
            if r.get(f) is not None:
                hist.append(r[f])


# ---------------------------------------------------------------- 1) rozsah + zbývající rozsah

def range_block(days: list[tuple[date, dict]]) -> dict:
    rs = [r for _, r in days if r.get("typ_range")]
    ratio = [r["range"] / r["typ_range"] for r in rs]
    out = {"n": len(rs), "ratio": quant(ratio, (0.1, 0.25, 0.5, 0.75, 0.9)),
           "ratio_q": [round(float(np.quantile(ratio, q)), 4) for q in QS] if ratio else [],
           "range_pct": quant([r["range"] for r in rs], (0.25, 0.5, 0.75, 0.9))}
    cps = {}
    for c in CHECKPOINTS:
        rows = [(r["cp"][c]["so_far"] / r["typ_range"], (r["range"] - r["cp"][c]["so_far"]) / r["typ_range"])
                for r in rs if c in r["cp"]]
        if len(rows) < 30:
            continue
        sf = np.array([x[0] for x in rows])
        ex = np.array([x[1] for x in rows])
        e1, e2 = (float(np.quantile(sf, 1 / 3)), float(np.quantile(sf, 2 / 3)))
        buckets = []
        for lo, hi in ((None, e1), (e1, e2), (e2, None)):
            m = np.ones(len(sf), bool)
            if lo is not None:
                m &= sf >= lo
            if hi is not None:
                m &= sf < hi
            buckets.append({"lo": None if lo is None else round(lo, 3), "hi": None if hi is None else round(hi, 3),
                            "ext": quant(ex[m], (0.25, 0.5, 0.75, 0.9))})
        cps[str(c)] = {"n": len(rows), "so_far_q": [round(float(np.quantile(sf, q)), 4) for q in QS],
                       "ext": quant(ex, (0.25, 0.5, 0.75, 0.9)), "buckets": buckets}
    out["checkpoints"] = cps
    return out


# ---------------------------------------------------------------- 2) RTH extrémy

def extremes_block(days: list[tuple[date, dict]], length: int) -> dict:
    rs = [r for _, r in days]
    n = len(rs)
    out = {"n": n}
    for w in (30, 60):
        hi = sum(r["t_high"] < w for r in rs)
        lo = sum(r["t_low"] < w for r in rs)
        both = sum(r["t_high"] < w and r["t_low"] < w for r in rs)
        out[f"first{w}"] = {"high": prop(hi, n), "low": prop(lo, n), "either": prop(hi + lo - both, n),
                            "both": prop(both, n)}
    slots = list(range(0, length, 30))
    out["slots"] = [{"from": s, "high": prop(sum(s <= r["t_high"] < s + 30 for r in rs), n),
                     "low": prop(sum(s <= r["t_low"] < s + 30 for r in rs), n)} for s in slots]
    cps = {}
    for c in CHECKPOINTS:
        rows = [r["cp"][c] for r in rs if c in r["cp"]]
        m = len(rows)
        if m < 30:
            continue
        hold_h = [x for x in rows if x["hi_age"] >= 30]
        hold_l = [x for x in rows if x["lo_age"] >= 30]
        cps[str(c)] = {
            "high_done": prop(sum(not x["new_high"] for x in rows), m),
            "low_done": prop(sum(not x["new_low"] for x in rows), m),
            "both_done": prop(sum(not x["new_high"] and not x["new_low"] for x in rows), m),
            # extrém stojí už aspoň 30 min (živě se dá ověřit) → šance, že vydrží do konce RTH
            "high_done_aged": prop(sum(not x["new_high"] for x in hold_h), len(hold_h)),
            "low_done_aged": prop(sum(not x["new_low"] for x in hold_l), len(hold_l)),
        }
    out["checkpoints"] = cps
    return out


# ---------------------------------------------------------------- 4) trendový den

def _strong(r: dict, der_min: float) -> str | None:
    """Trendový den s prahem DER z dat (horních 10 % dní) — pracovní práh 0,5 z dokumentu NQ
    reálně skoro nenastává (medián DER ≈ náhodná procházka 1/√N)."""
    if r["c"] > r["o"] and r["der"] >= der_min and r["cl"] >= TREND_CL and r["retr"] <= TREND_RETR:
        return "bull"
    if r["c"] < r["o"] and r["der"] >= der_min and r["cl"] <= 1 - TREND_CL and r["retr"] <= TREND_RETR:
        return "bear"
    return None


def trend_block(days: list[tuple[date, dict]]) -> dict:
    rs = [r for _, r in days]
    n = len(rs)
    ders = [r["der"] for r in rs]
    der90 = float(np.quantile(ders, 0.9)) if ders else 1.0
    for r in rs:
        r["strong"] = _strong(r, der90)
    n_steps = int(np.median([r["n_steps"] for r in rs])) if rs else 0
    cl_b = [(0.8, 1.01, "near_high"), (0.6, 0.8, "upper"), (0.4, 0.6, "mid"), (0.2, 0.4, "lower"), (-0.01, 0.2, "near_low")]
    rt_b = [(0, 0.25, "shallow"), (0.25, 0.5, "moderate"), (0.5, 0.75, "deep"), (0.75, 10, "full")]
    f30 = [r["cp"][30]["cont"] for r in rs if 30 in r["cp"] and r["cp"][30]["cont"] is not None]
    out = {
        "n": n,
        "der": quant(ders, (0.1, 0.25, 0.5, 0.75, 0.9)),
        "der_random_walk": round(1 / math.sqrt(n_steps), 3) if n_steps else None,
        "der_share": {k: prop(sum(lo <= x < hi for x in ders), n)
                      for lo, hi, k in ((0, 0.25, "low"), (0.25, 0.5, "mixed"), (0.5, 0.7, "high"), (0.7, 1.01, "very_high"))},
        "close_location": {k: prop(sum(lo <= r["cl"] < hi for r in rs), n) for lo, hi, k in cl_b},
        "retracement": {k: prop(sum(lo <= r["retr"] < hi for r in rs), n) for lo, hi, k in rt_b},
        "trend_day": {"bull": prop(sum(r["trend"] == "bull" for r in rs), n),
                      "bear": prop(sum(r["trend"] == "bear" for r in rs), n),
                      "any": prop(sum(r["trend"] is not None for r in rs), n)},
        "strong_day": {"bull": prop(sum(r["strong"] == "bull" for r in rs), n),
                       "bear": prop(sum(r["strong"] == "bear" for r in rs), n),
                       "any": prop(sum(r["strong"] is not None for r in rs), n)},
        "first30_continuation": prop(sum(bool(x) for x in f30), len(f30)),
        "definition": {"der_min": TREND_DER, "cl_min": TREND_CL, "retr_max": TREND_RETR,
                       "strong_der_min": round(der90, 3)},
    }
    cps = {}
    for c in CHECKPOINTS:
        rows = [(r["cp"][c]["der"], r["strong"] is not None and (r["strong"] == "bull") == (r["cp"][c]["move"] > 0),
                 r["cp"][c]["cont"]) for r in rs if c in r["cp"] and r["cp"][c]["move"] != 0]
        if len(rows) < 30:
            continue
        dc = np.array([x[0] for x in rows])
        e1, e2 = float(np.quantile(dc, 1 / 3)), float(np.quantile(dc, 2 / 3))
        bks = []
        for lo, hi in ((None, e1), (e1, e2), (e2, None)):
            sel = [x for x in rows if (lo is None or x[0] >= lo) and (hi is None or x[0] < hi)]
            bks.append({"lo": None if lo is None else round(lo, 3), "hi": None if hi is None else round(hi, 3),
                        "trend_day": prop(sum(x[1] for x in sel), len(sel)),
                        "continues": prop(sum(bool(x[2]) for x in sel), len(sel))})
        cps[str(c)] = {"n": len(rows), "buckets": bks}
    out["checkpoints"] = cps
    return out


# ---------------------------------------------------------------- 5) makro dny

MACRO_WINDOWS = {"fomc": "after14", "cpi": "first30", "nfp": "first30", "ppi": "first30"}


def macro_block(days: list[tuple[date, dict]], events: dict[str, set[date]]) -> dict:
    tagged = {d: {k for k, ds in events.items() if d in ds} for d, _ in days}
    out = {}
    base_rows = [r for d, r in days if not tagged[d] and r.get("typ_range")]
    base = [r["range"] / r["typ_range"] for r in base_rows]
    out["none"] = {"n": len(base), "rth": quant(base, (0.25, 0.5, 0.75)), "rth_ci": boot_median_ci(base)}
    p90 = float(np.quantile(base, 0.9)) if len(base) >= 30 else None
    for k, ds in events.items():
        rows = [r for d, r in days if d in ds and r.get("typ_range")]
        rat = [r["range"] / r["typ_range"] for r in rows]
        w = MACRO_WINDOWS.get(k)
        wr = [r[w] / r[f"typ_{w}"] for r in rows if w and r.get(w) is not None and r.get(f"typ_{w}")]
        wb = [r[w] / r[f"typ_{w}"] for r in base_rows if w and r.get(w) is not None and r.get(f"typ_{w}")]
        out[k] = {"n": len(rat), "rth": quant(rat, (0.25, 0.5, 0.75)), "rth_ci": boot_median_ci(rat),
                  "big_day": prop(sum(x > p90 for x in rat), len(rat)) if p90 else None,
                  "window": w, "win": quant(wr, (0.25, 0.5, 0.75)), "win_ci": boot_median_ci(wr),
                  "win_none": quant(wb, (0.5,))}
    out["_big_day_ratio"] = round(p90, 3) if p90 else None
    return out


# ---------------------------------------------------------------- 3) sessions Asia → London → NY

def _rng(sub: pd.DataFrame):
    return (float(sub["high"].max()), float(sub["low"].min())) if len(sub) else (None, None)


def session_days(bars: pd.DataFrame, src: str) -> dict[date, dict]:
    b = bars if "tday" in bars else prep(bars)
    out = {}
    for td, day in b.groupby("tday"):
        if pd.Timestamp(td).weekday() > 4:
            continue
        w = {k: day[(day["hour_et"] >= s) & (day["hour_et"] < e)
                    & ((day["et_date"] < td) if k == "asia" else (day["et_date"] == td))]
             for k, (s, e) in SESSION_WINDOWS.items()}
        need = {"asia": 40, "pre": 20, "london": 30, "ny": 85}
        if any(len(w[k]) < need[k] for k in need):
            continue
        ah, al = _rng(w["asia"])
        ph, pl = _rng(w["pre"])
        lh, ll = _rng(w["london"])
        ny = w["ny"]
        o = float(w["asia"]["open"].iloc[0])
        brk_h, brk_l = lh > ah, ll < al
        scen = "both" if brk_h and brk_l else "high_only" if brk_h else "low_only" if brk_l else "inside"
        hi_hit = ny.index[ny["high"].to_numpy() > lh]
        lo_hit = ny.index[ny["low"].to_numpy() < ll]
        out[td] = {
            "src": src, "asia_range": (ah - al) / o * 100,
            "pre_high": bool(ph > ah), "pre_low": bool(pl < al),
            "london_high": bool(brk_h), "london_low": bool(brk_l),
            # „pokračování“ po Pre-London: London udělá nový extrém za extrémem Pre-London na proražené straně
            "london_ext_high": bool(lh > ph), "london_ext_low": bool(ll < pl),
            "scenario": scen,
            "ny_lh": len(hi_hit) > 0, "ny_ll": len(lo_hit) > 0,
            "ny_first": None if not len(hi_hit) and not len(lo_hit) else
                        ("high" if not len(lo_hit) or (len(hi_hit) and hi_hit[0] < lo_hit[0]) else "low"),
        }
    return out


def sessions_block(sdays: list[tuple[date, dict]]) -> dict:
    hist: list[float] = []
    for _, r in sdays:          # úzká Asie = pod 33. percentilem typické Asie (předchozích 20 dní)
        r["asia_norm"] = r["asia_range"] / float(np.median(hist[-TYPICAL_N:])) if len(hist) >= TYPICAL_MIN else None
        hist.append(r["asia_range"])
    rs = [r for _, r in sdays]
    n = len(rs)
    norms = [r["asia_norm"] for r in rs if r["asia_norm"] is not None]
    narrow_edge = float(np.quantile(norms, 1 / 3)) if len(norms) >= 30 else None

    def cond(sel, key):
        return prop(sum(bool(r[key]) for r in sel), len(sel))

    narrow = [r for r in rs if narrow_edge is not None and r["asia_norm"] is not None and r["asia_norm"] < narrow_edge]
    ph, pl = [r for r in rs if r["pre_high"]], [r for r in rs if r["pre_low"]]
    out = {
        "n": n,
        "windows_et": {k: list(v) for k, v in SESSION_WINDOWS.items()},
        "london_vs_asia": {"high": cond(rs, "london_high"), "low": cond(rs, "london_low"),
                           "both": prop(sum(r["scenario"] == "both" for r in rs), n),
                           "inside": prop(sum(r["scenario"] == "inside" for r in rs), n)},
        "pre_london": {
            "pre_high": cond(rs, "pre_high"), "pre_low": cond(rs, "pre_low"),
            "after_pre_high": {"london_ext_high": cond(ph, "london_ext_high"), "london_low": cond(ph, "london_low")},
            "after_pre_low": {"london_ext_low": cond(pl, "london_ext_low"), "london_high": cond(pl, "london_high")},
            "narrow_after_pre_high": cond([r for r in narrow if r["pre_high"]], "london_ext_high"),
            "narrow_after_pre_low": cond([r for r in narrow if r["pre_low"]], "london_ext_low"),
            "narrow_edge": round(narrow_edge, 3) if narrow_edge else None,
        },
        "ny_by_scenario": {},
    }
    for sc in ("both", "inside", "high_only", "low_only"):
        sel = [r for r in rs if r["scenario"] == sc]
        out["ny_by_scenario"][sc] = {"n": len(sel), "share": prop(len(sel), n),
                                     "ny_london_high": cond(sel, "ny_lh"), "ny_london_low": cond(sel, "ny_ll")}
    sel = [r for r in rs if r["scenario"] == "high_only" and r["ny_first"] == "low"]
    out["high_only_low_first"] = cond(sel, "ny_lh")
    sel = [r for r in rs if r["scenario"] == "low_only" and r["ny_first"] == "high"]
    out["low_only_high_first"] = cond(sel, "ny_ll")
    out["from"] = str(sdays[0][0]) if sdays else None
    out["to"] = str(sdays[-1][0]) if sdays else None
    return out


# ---------------------------------------------------------------- vše dohromady

def compute_edge(rth_sources: list[tuple[str, pd.DataFrame]], session_sources: list[tuple[str, pd.DataFrame]],
                 rth: tuple[float, float], events: dict[str, set[date]], ref_price: float | None) -> dict:
    """rth_sources/session_sources = [(název zdroje, bary)], v pořadí priority."""
    length = int(round((rth[1] - rth[0]) * 60))
    days = merge_days(*[rth_days(prep(b), rth, name) for name, b in rth_sources if b is not None and len(b)])
    add_typical(days)
    srcs: dict[str, int] = {}
    for _, r in days:
        srcs[r["src"]] = srcs.get(r["src"], 0) + 1
    last20 = [r["range"] for _, r in days[-TYPICAL_N:]]
    out = {
        "meta": {"rth_et": list(rth), "days": len(days), "from": str(days[0][0]) if days else None,
                 "to": str(days[-1][0]) if days else None, "sources": srcs,
                 "ref_price": ref_price,
                 "typical_range_pct": round(float(np.median(last20)), 4) if last20 else None,
                 "typical_first30_pct": round(float(np.median([r["first30"] for _, r in days[-TYPICAL_N:] if r.get("first30")])), 4) if days else None,
                 "typical_after14_pct": (round(float(np.median(a14)), 4)
                                         if (a14 := [r["after14"] for _, r in days[-TYPICAL_N:] if r.get("after14")]) else None),
                 "checkpoints": CHECKPOINTS, "qs": QS},
    }
    if days:
        out["range"] = range_block(days)
        out["extremes"] = extremes_block(days, length)
        out["trend"] = trend_block(days)
        out["macro"] = macro_block(days, events)
    sdays = merge_days(*[session_days(prep(b), name) for name, b in session_sources if b is not None and len(b)])
    if len(sdays) >= 30:
        out["sessions"] = sessions_block(sdays)
    return out


def load_events(path) -> dict[str, set[date]]:
    import json
    raw = json.loads(open(path, encoding="utf-8").read())
    return {k: {date.fromisoformat(x) for x in v} for k, v in raw.get("events", {}).items()}


# ---------------------------------------------------------------- živý stav dne

def _checkpoint_for(elapsed: int) -> int | None:
    past = [c for c in CHECKPOINTS if c <= elapsed]
    return past[-1] if past else None


def _bucket(buckets: list[dict], v: float) -> dict | None:
    for b in buckets:
        if (b["lo"] is None or v >= b["lo"]) and (b["hi"] is None or v < b["hi"]):
            return b
    return None


def live_state(bars: pd.DataFrame, edge: dict, now: datetime, events_today: list[str],
               price_scale: float | None = None) -> dict:
    """Dnešní stav vůči historii. bars = dnešní 5min bary (UTC ts), ideálně od 18:00 ET předchozího dne.
    price_scale = cena instrumentu pro převod % → body (jinak se použije cena z barů)."""
    m = edge["meta"]
    rth = m["rth_et"]
    open_min, length = int(round(rth[0] * 60)), int(round((rth[1] - rth[0]) * 60))
    b = prep(bars)
    now_et = pd.Timestamp(now).tz_convert(TZ)
    today = now_et.date() if now_et.hour < 18 else (now_et + pd.Timedelta(hours=6)).date()
    nmin = now_et.hour * 60 + now_et.minute
    out: dict = {"date": str(today), "now_et": now_et.strftime("%H:%M"), "events": events_today}
    day = b[b["et_date"] == today]
    rth_bars = day[(day["et_min"] >= open_min) & (day["et_min"] < open_min + length) & (day["et_min"] + 5 <= nmin)]
    elapsed = nmin - open_min
    out["phase"] = "pre" if elapsed < 0 else "rth" if elapsed < length else "post"
    price = float(b["close"].iloc[-1]) if len(b) else None
    out["price"] = price
    scale = price_scale or price
    typ = m.get("typical_range_pct")

    def pts(pct):
        return round(pct / 100 * scale, 1) if pct is not None and scale else None

    out["typical_range_pts"] = pts(typ)
    if len(rth_bars) and typ:
        o = float(rth_bars["open"].iloc[0])
        H, L = float(rth_bars["high"].max()), float(rth_bars["low"].min())
        so_far = (H - L) / o * 100
        t = rth_bars["et_min"].to_numpy() - open_min
        c_arr = rth_bars["close"].to_numpy(float)
        steps = np.abs(np.diff(np.concatenate([[o], c_arr])))
        last = float(c_arr[-1])
        der = float(abs(last - o) / steps.sum()) if steps.sum() > 0 else 0.0
        rr = {"open": o, "high": H, "low": L, "so_far_pts": pts(so_far), "so_far_pct": round(so_far, 3),
              "vs_typical": round(so_far / typ, 2),
              "t_high": int(t[int(np.argmax(rth_bars["high"].to_numpy()))]),
              "t_low": int(t[int(np.argmin(rth_bars["low"].to_numpy()))])}
        cp = _checkpoint_for(min(elapsed, length))
        rb = edge.get("range", {})
        cps = rb.get("checkpoints", {})
        ratio, rq = so_far / typ, rb.get("ratio", {})
        # zařazení dne podle dosavadního (po zavření konečného) rozsahu vůči typickému dni
        if rq.get("p90") is not None:
            rr["category"] = "extreme" if ratio > rq["p90"] else "above" if ratio > rq["p75"] else "normal"
            rr["category_edges"] = {"p75": rq["p75"], "p90": rq["p90"]}
        if out["phase"] == "post":
            rr["final_percentile"] = percentile_of(ratio, rb.get("ratio_q") or [])
            cp = None                              # zbývající rozsah po zavření nedává smysl
        if cp and str(cp) in cps:
            c = cps[str(cp)]
            sfn = so_far / typ
            bk = _bucket(c["buckets"], sfn)
            rr["checkpoint"] = cp
            rr["percentile"] = percentile_of(sfn, c["so_far_q"])
            if bk and bk["ext"].get("n"):
                rr["remaining_pts"] = {k: pts(bk["ext"][k] * typ) for k in ("p25", "p50", "p75", "p90")}
                rr["remaining_n"] = bk["ext"]["n"]
        out["range"] = rr
        ex = edge.get("extremes", {}).get("checkpoints", {})
        if cp and str(cp) in ex:
            e = ex[str(cp)]
            closed = int(t[-1]) + 5                  # konec posledního uzavřeného baru (min od open)
            hi_age, lo_age = closed - rr["t_high"], closed - rr["t_low"]
            out["extremes"] = {"checkpoint": cp, "hi_age": hi_age, "lo_age": lo_age,
                               "high_holds": e["high_done_aged"] if hi_age >= 30 else e["high_done"],
                               "low_holds": e["low_done_aged"] if lo_age >= 30 else e["low_done"],
                               "both_hold": e["both_done"]}
        tr = edge.get("trend", {}).get("checkpoints", {})
        cl = (last - L) / (H - L) if H > L else None
        out["trend"] = {"der": round(der, 2), "close_location": round(cl, 2) if cl is not None else None,
                        "direction": "up" if last > o else "down" if last < o else "flat"}
        if cp and str(cp) in tr and last != o:
            bk = _bucket(tr[str(cp)]["buckets"], der)
            if bk:
                out["trend"].update({"checkpoint": cp, "p_trend_day": bk["trend_day"], "p_continues": bk["continues"]})
    # sessions (Asia → Pre-London → London → NY)
    sb = edge.get("sessions")
    if sb:
        tb = b[b["tday"] == today]

        def win(k):
            s, e = SESSION_WINDOWS[k]
            sub = tb[(tb["hour_et"] >= s) & (tb["hour_et"] < e) & ((tb["et_date"] < today) if k == "asia" else (tb["et_date"] == today))]
            return sub

        a, p, lo_ = win("asia"), win("pre"), win("london")
        ss: dict = {}
        if len(a):
            ah, al = _rng(a)
            ss.update({"asia_high": ah, "asia_low": al})
            if len(p) and nmin >= 120:
                ph, pl = _rng(p)
                ss["pre"] = "high" if ph > ah and not pl < al else "low" if pl < al and not ph > ah else \
                    "both" if ph > ah and pl < al else "inside"
                if ss["pre"] == "high":
                    ss["pre_stat"] = sb["pre_london"]["after_pre_high"]["london_ext_high"]
                elif ss["pre"] == "low":
                    ss["pre_stat"] = sb["pre_london"]["after_pre_low"]["london_ext_low"]
            if len(lo_) and nmin >= 300:
                lh, ll = _rng(lo_)
                bh, bl = lh > ah, ll < al
                scen = "both" if bh and bl else "high_only" if bh else "low_only" if bl else "inside"
                ss.update({"london_high": lh, "london_low": ll, "scenario": scen,
                           "scenario_stat": sb["ny_by_scenario"][scen]})
                ny = tb[(tb["hour_et"] >= 8) & (tb["hour_et"] < 16) & (tb["et_date"] == today)]
                if len(ny):
                    took_h, took_l = bool(float(ny["high"].max()) > lh), bool(float(ny["low"].min()) < ll)
                    ss.update({"ny_took_london_high": took_h, "ny_took_london_low": took_l})
                    if scen == "high_only" and took_l and not took_h:
                        ss["conditional"] = {"text": "high_only_low_first", **sb["high_only_low_first"]}
                    if scen == "low_only" and took_h and not took_l:
                        ss["conditional"] = {"text": "low_only_high_first", **sb["low_only_high_first"]}
        out["sessions"] = ss
    mb = edge.get("macro", {})
    out["macro"] = [{"event": ev, **{k: mb[ev].get(k) for k in ("n", "rth", "rth_ci", "window", "win")}}
                    for ev in events_today if ev in mb]
    return out
