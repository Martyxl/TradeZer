"""Výpočet market statistik z Dukascopy 5m barů (styl FM PETR Market Statistics).

Vstup:  data/raw/<instrument>-m5-*.csv  (timestamp ms, open, high, low, close, volume)
Výstup: web/public/stats/<key>.json  + agregované 15m/1h CSV v data/agg/

Obchodní den začíná 22:00 UTC (FX/Globex konvence).
Sessions (UTC):
  NQ (futures):  Asia 00–07, London 07–12, NY 12–21, Close = zbytek
  GOLD (spot):   Asia 22–07, London 07–12, NY 12–21, Close = 21–22
"""
from __future__ import annotations

import glob
import json
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
RAW = ROOT / "raw"
AGG = ROOT / "agg"
OUT = ROOT.parent / "web" / "public" / "stats"

DAY_SHIFT_H = 2  # posun: 22:00 UTC -> 00:00 "trading day"

INSTRUMENTS = {
    "nq": {
        "file_glob": "usatechidxusd-m5-*.csv",
        "label": "NAS/DAQ (US Tech 100)",
        "unit": "bodů",
        "sessions": {"asia": (0, 7), "london": (7, 12), "ny": (12, 21)},
        "rth": (13.5, 20.0),   # NY RTH v UTC
    },
    "gold": {
        "file_glob": "xauusd-m5-*.csv",
        "label": "GOLD (XAU/USD)",
        "unit": "bodů",
        "sessions": {"asia": (22, 7), "london": (7, 12), "ny": (12, 21)},
        "rth": (13.5, 18.5),   # COMEX RTH v UTC
    },
}

WEEKDAYS_CZ = ["Po", "Út", "St", "Čt", "Pá"]


def load_m5(pattern: str) -> pd.DataFrame:
    files = sorted(glob.glob(str(RAW / pattern)))
    if not files:
        raise FileNotFoundError(f"Chybí data: {pattern}")
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    df = df.drop_duplicates(subset="timestamp").sort_values("timestamp")
    df["ts"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    if "volume" not in df.columns:
        df["volume"] = 1.0
    df["volume"] = df["volume"].fillna(0.0)
    # trading day: 22:00 UTC -> půlnoc
    shifted = df["ts"] + pd.Timedelta(hours=DAY_SHIFT_H)
    df["tday"] = shifted.dt.date
    df["tweekday"] = shifted.dt.weekday  # 0=Po
    df["tweek"] = shifted.dt.strftime("%G-%V")
    df["hour"] = df["ts"].dt.hour
    df["hour_f"] = df["ts"].dt.hour + df["ts"].dt.minute / 60.0
    df["tp"] = (df["high"] + df["low"] + df["close"]) / 3.0
    # vyhoď víkendové zbytky (trading day so/ne)
    df = df[df["tweekday"] <= 4].reset_index(drop=True)
    return df


def aggregate(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    g = df.set_index("ts").resample(freq).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    ).dropna(subset=["open"])
    return g.reset_index()


def in_session(hour_f: pd.Series, start: float, end: float) -> pd.Series:
    if start < end:
        return (hour_f >= start) & (hour_f < end)
    return (hour_f >= start) | (hour_f < end)  # přes půlnoc


def pct(n: int, total: int) -> float:
    return round(100.0 * n / total, 1) if total else 0.0


def dist_pct(counts: dict[str, int]) -> dict[str, float]:
    total = sum(counts.values())
    return {k: pct(v, total) for k, v in counts.items()}


# ---------------------------------------------------------------- statistiky

def session_sizes(df: pd.DataFrame, sessions: dict) -> dict:
    out = {}
    for name, (s, e) in sessions.items():
        mask = in_session(df["hour_f"], s, e)
        sub = df[mask]
        rng = sub.groupby("tday").agg(h=("high", "max"), l=("low", "min"))
        sizes = (rng["h"] - rng["l"]).dropna()
        out[name] = {
            "avg": round(float(sizes.mean()), 1),
            "median": round(float(sizes.median()), 1),
            "min": round(float(sizes.min()), 1),
            "max": round(float(sizes.max()), 1),
        }
    return out


def daily_extreme_session(df: pd.DataFrame, sessions: dict, col: str) -> dict:
    """Ve které session se tiskne denní high (col='high') / low (col='low')."""
    counts = {name: 0 for name in sessions} | {"close": 0}
    for _, day in df.groupby("tday"):
        idx = day[col].idxmax() if col == "high" else day[col].idxmin()
        hf = day.loc[idx, "hour_f"]
        hit = None
        for name, (s, e) in sessions.items():
            ok = (s <= hf < e) if s < e else (hf >= s or hf < e)
            if ok:
                hit = name
                break
        counts[hit or "close"] += 1
    return dist_pct(counts)


def _revisit_bucket(days: list[pd.DataFrame], level: float, start_pos: int, same_day: pd.DataFrame | None) -> str:
    """Vrátí bucket: same/1/2/3/never. same_day = zbytek dne po vzniku levelu."""
    if same_day is not None and len(same_day) and ((same_day["low"] <= level) & (same_day["high"] >= level)).any():
        return "same"
    for i, d in enumerate(days[:3], start=1):
        if len(d) and ((d["low"] <= level) & (d["high"] >= level)).any():
            return str(i)
    return "never"


def daily_open_revisit(df: pd.DataFrame) -> dict:
    counts = {"same": 0, "1": 0, "2": 0, "3": 0, "never": 0}
    tdays = sorted(df["tday"].unique())
    by_day = {d: g for d, g in df.groupby("tday")}
    for i, d in enumerate(tdays):
        day = by_day[d]
        if len(day) < 5:
            continue
        open_price = float(day.iloc[0]["open"])
        # same day: po prvním baru se cena vrátí na open (nejdřív ale musí odejít)
        rest = day.iloc[1:]
        away = rest[(rest["low"] > open_price) | (rest["high"] < open_price)]
        if len(away):
            after = rest.loc[away.index[0]:]
            bucket = _revisit_bucket([by_day[t] for t in tdays[i+1:i+4]], open_price, 0, after)
        else:
            bucket = "same"  # nikdy neodešla od open
        counts[bucket] += 1
    return dist_pct(counts)


def candle_hl_revisit(daily: pd.DataFrame) -> dict:
    """U každé denní svíčky — kdy je high/low znovu otestováno (den 1–3, ne do 3 dnů)."""
    counts = {"1": 0, "2": 0, "3": 0, "never": 0}
    levels = 0
    arr = daily[["high", "low"]].to_numpy()
    for i in range(len(daily) - 3):
        for col in (0, 1):
            level = arr[i][col]
            levels += 1
            hit = "never"
            for j in range(1, 4):
                lo, hi = arr[i + j][1], arr[i + j][0]
                if lo <= level <= hi:
                    hit = str(j)
                    break
            counts[hit] += 1
    return {"levels": levels, **dist_pct(counts)}


def _poc(sub: pd.DataFrame, bin_width: float) -> float | None:
    if len(sub) < 3 or sub["volume"].sum() <= 0:
        return None
    bins = (sub["tp"] / bin_width).round().astype(int)
    vol = sub.groupby(bins)["volume"].sum()
    return float(vol.idxmax()) * bin_width


def daily_npoc_revisit(df: pd.DataFrame, bin_width: float) -> dict:
    counts = {"1": 0, "2": 0, "3": 0, "never": 0}
    tdays = sorted(df["tday"].unique())
    by_day = {d: g for d, g in df.groupby("tday")}
    n = 0
    for i, d in enumerate(tdays[:-1]):
        poc = _poc(by_day[d], bin_width)
        if poc is None:
            continue
        n += 1
        hit = "never"
        for j, t in enumerate(tdays[i+1:i+4], start=1):
            day = by_day[t]
            if ((day["low"] <= poc) & (day["high"] >= poc)).any():
                hit = str(j)
                break
        counts[hit] += 1
    return {"days": n, **dist_pct(counts)}


def session_npoc_revisit(df: pd.DataFrame, sessions: dict, bin_width: float) -> dict:
    out = {}
    tdays = sorted(df["tday"].unique())
    by_day = {d: g for d, g in df.groupby("tday")}
    for name, (s, e) in sessions.items():
        counts = {"same": 0, "1": 0, "2": 0, "3": 0, "never": 0}
        n = 0
        for i, d in enumerate(tdays):
            day = by_day[d]
            mask = in_session(day["hour_f"], s, e)
            sub = day[mask]
            poc = _poc(sub, bin_width)
            if poc is None:
                continue
            n += 1
            # zbytek dne po session
            after = day.loc[sub.index[-1]:].iloc[1:] if len(sub) else day.iloc[0:0]
            bucket = _revisit_bucket([by_day[t] for t in tdays[i+1:i+4]], poc, 0, after)
            counts[bucket] += 1
        out[name] = {"days": n, **dist_pct(counts)}
    return out


def vwap_edge_revisit(df: pd.DataFrame) -> dict:
    counts = {"same": 0, "1": 0, "2": 0, "3": 0, "never": 0}
    tdays = sorted(df["tday"].unique())
    by_day = {d: g for d, g in df.groupby("tday")}
    n = 0
    for i, d in enumerate(tdays):
        day = by_day[d].reset_index(drop=True)
        if len(day) < 10:
            continue
        vol = day["volume"].to_numpy()
        tp = day["tp"].to_numpy()
        cum_v = np.cumsum(vol)
        cum_v[cum_v == 0] = 1e-9
        vwap = np.cumsum(tp * vol) / cum_v
        var = np.cumsum(vol * (tp - vwap) ** 2) / cum_v
        sigma = np.sqrt(var)
        upper, lower = vwap + sigma, vwap - sigma
        touch = np.where((day["high"].to_numpy() >= upper) | (day["low"].to_numpy() <= lower))[0]
        touch = touch[touch > 3]  # ignoruj prvních pár barů (sigma ~ 0)
        if len(touch) == 0:
            continue
        n += 1
        t0 = touch[0]
        rest = day.iloc[t0 + 1:]
        final_vwap = float(vwap[-1])
        returned = ((rest["low"].to_numpy() <= vwap[t0 + 1:]) & (rest["high"].to_numpy() >= vwap[t0 + 1:])).any() if len(rest) else False
        if returned:
            counts["same"] += 1
            continue
        hit = "never"
        for j, t in enumerate(tdays[i+1:i+4], start=1):
            nxt = by_day[t]
            if ((nxt["low"] <= final_vwap) & (nxt["high"] >= final_vwap)).any():
                hit = str(j)
                break
        counts[hit] += 1
    return {"days": n, **dist_pct(counts)}


def weekly_extreme_day(df: pd.DataFrame, col: str) -> dict:
    counts = {d: 0 for d in WEEKDAYS_CZ}
    for _, wk in df.groupby("tweek"):
        idx = wk[col].idxmax() if col == "high" else wk[col].idxmin()
        wd = int(wk.loc[idx, "tweekday"])
        if wd <= 4:
            counts[WEEKDAYS_CZ[wd]] += 1
    return dist_pct(counts)


def weekly_open_revisit(df: pd.DataFrame) -> dict:
    counts = {d: 0 for d in WEEKDAYS_CZ} | {"Nikdy": 0}
    for _, wk in df.groupby("tweek"):
        wk = wk.reset_index(drop=True)
        if len(wk) < 20:
            continue
        open_price = float(wk.iloc[0]["open"])
        rest = wk.iloc[1:]
        away = rest[(rest["low"] > open_price) | (rest["high"] < open_price)]
        if not len(away):
            counts["Po"] += 1
            continue
        after = rest.loc[away.index[0]:]
        hits = after[(after["low"] <= open_price) & (after["high"] >= open_price)]
        if len(hits):
            wd = int(hits.iloc[0]["tweekday"])
            counts[WEEKDAYS_CZ[min(wd, 4)]] += 1
        else:
            counts["Nikdy"] += 1
    return dist_pct(counts)


def range_break_stats(df: pd.DataFrame, range_hours: tuple, break_hours: tuple) -> dict:
    """Obě strany / pouze high / pouze low / ani jedna + pořadí prolomení."""
    counts = {"both": 0, "high_only": 0, "low_only": 0, "neither": 0}
    order = {"low_to_high": 0, "high_to_low": 0}
    n = 0
    for _, day in df.groupby("tday"):
        rmask = in_session(day["hour_f"], *range_hours)
        bmask = in_session(day["hour_f"], *break_hours)
        rng, brk = day[rmask], day[bmask]
        if len(rng) < 3 or len(brk) < 3:
            continue
        n += 1
        hi, lo = float(rng["high"].max()), float(rng["low"].min())
        hi_hits = brk[brk["high"] > hi]
        lo_hits = brk[brk["low"] < lo]
        if len(hi_hits) and len(lo_hits):
            counts["both"] += 1
            if lo_hits.index[0] < hi_hits.index[0]:
                order["low_to_high"] += 1
            else:
                order["high_to_low"] += 1
        elif len(hi_hits):
            counts["high_only"] += 1
        elif len(lo_hits):
            counts["low_only"] += 1
        else:
            counts["neither"] += 1
    return {"days": n, **dist_pct(counts), "order": dist_pct(order)}


def by_hour(df: pd.DataFrame) -> dict:
    rng = df.groupby("hour").apply(lambda g: (g["high"] - g["low"]).mean() * 12, include_groups=False)
    vol = df.groupby("hour")["volume"].mean()
    hours = list(range(24))
    return {
        "volatility": [round(float(rng.get(h, 0.0)), 1) for h in hours],
        "volume": [round(float(vol.get(h, 0.0)), 1) for h in hours],
    }


def compute(key: str, cfg: dict) -> dict:
    df = load_m5(cfg["file_glob"])
    daily = df.groupby("tday").agg(
        open=("open", "first"), high=("high", "max"),
        low=("low", "min"), close=("close", "last"), volume=("volume", "sum"),
    ).reset_index()

    # uložit agregované timeframy
    AGG.mkdir(parents=True, exist_ok=True)
    for freq, tf in (("15min", "m15"), ("1h", "h1")):
        aggregate(df, freq).to_csv(AGG / f"{key}-{tf}.csv", index=False)

    med_range = float((daily["high"] - daily["low"]).median())
    bin_width = max(med_range / 100.0, 1e-4)

    sessions = cfg["sessions"]
    ov_start = 22.0
    rth = cfg["rth"]

    meta = {
        "instrument": key.upper(),
        "label": cfg["label"],
        "unit": cfg["unit"],
        "from": str(df["ts"].min())[:10],
        "to": str(df["ts"].max())[:10],
        "bars_m5": int(len(df)),
        "days": int(df["tday"].nunique()),
        "weeks": int(df["tweek"].nunique()),
    }
    return {
        "meta": meta,
        "session_sizes": session_sizes(df, sessions),
        "daily_high_session": daily_extreme_session(df, sessions, "high"),
        "daily_low_session": daily_extreme_session(df, sessions, "low"),
        "daily_open_revisit": daily_open_revisit(df),
        "candle_hl_revisit": candle_hl_revisit(daily),
        "daily_npoc_revisit": daily_npoc_revisit(df, bin_width),
        "session_npoc_revisit": session_npoc_revisit(df, sessions, bin_width),
        "vwap_edge_revisit": vwap_edge_revisit(df),
        "weekly_high_day": weekly_extreme_day(df, "high"),
        "weekly_low_day": weekly_extreme_day(df, "low"),
        "weekly_open_revisit": weekly_open_revisit(df),
        "asia_both_sides": range_break_stats(df, sessions["asia"], (7, 21)),
        "globex_both_sides": range_break_stats(df, (ov_start, rth[0]), rth),
        "by_hour": by_hour(df),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    keys = sys.argv[1:] or list(INSTRUMENTS)
    for key in keys:
        cfg = INSTRUMENTS[key]
        print(f"== {key}: počítám…")
        stats = compute(key, cfg)
        out_file = OUT / f"{key}.json"
        out_file.write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"   -> {out_file} ({stats['meta']['bars_m5']} barů, {stats['meta']['days']} dní)")


if __name__ == "__main__":
    main()
