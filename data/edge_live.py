"""Živý „den v číslech“ pro NQ / YM / GOLD → backend (PUT /api/marketstats/live/<key>).

Každé 2 minuty (obchodní den 20:00 → 16:35 ET) vezme dnešní 5min bary, porovná je s historií
z compute_stats (blok `edge`) a pošle: kolik dnešní rozsah odpovídá typickému dni a kolik
historicky zbývá, jestli už high/low pravděpodobně stojí, trendovost dne, scénář Asia → London
→ NY a dnešní makro události. Výpočet = edge_stats.live_state (testovaný).

Zdroje barů (pořadí = priorita):
  nq / ym — Yahoo futures NQ=F / YM=F (body + noc; Twelve Data futures nemá),
            záloha Twelve Data QQQ / DIA (jen RTH, body přepočtené referenční cenou z historie)
  gold    — Twelve Data XAU/USD (placený, 24 h), záloha Yahoo GC=F

Bezpečnost: jen odchozí spojení (Yahoo, TD, tradezer.app). O víkendu (pá 17:30 → ne 16:00 ET)
nic neposílá, ať Neon může spát.

Env: TRADEZER_TOKEN, TWELVEDATA_API_KEY (volitelný), TRADEZER_BASE_URL, STATS_OUT (default ~/tradezer/stats/out)
Použití: python edge_live.py [--loop] [klíč ...]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

import edge_stats

ET = ZoneInfo("America/New_York")
BASE = os.environ.get("TRADEZER_BASE_URL", "https://tradezer.app").rstrip("/")
TOKEN = os.environ.get("TRADEZER_TOKEN", "")
TD_KEY = os.environ.get("TWELVEDATA_API_KEY", "").strip()
STATS_OUT = Path(os.environ.get("STATS_OUT") or Path.home() / "tradezer" / "stats" / "out")
MACRO = Path(__file__).parent / "macro_dates.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TradezerStats/1.0"
SOURCES = {
    "nq": [("yahoo", "NQ=F"), ("twelvedata", "QQQ")],
    "ym": [("yahoo", "YM=F"), ("twelvedata", "DIA")],
    "gold": [("twelvedata", "XAU/USD"), ("yahoo", "GC=F")],
}
# Titulky z kalendáře (výhled na dashboardu) → typ události v historii
EVENT_WORDS = {"fomc": ("fomc", "federal funds rate"), "cpi": ("cpi",), "nfp": ("non-farm", "nonfarm"),
               "ppi": ("ppi",)}


def _get_json(url: str, headers: dict | None = None, timeout: int = 30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def yahoo_bars(symbol: str) -> pd.DataFrame:
    res = _get_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
                    "?range=2d&interval=5m&includePrePost=true")["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    rows = [(ts, q["open"][i], q["high"][i], q["low"][i], q["close"][i])
            for i, ts in enumerate(res.get("timestamp") or [])
            if None not in (q["open"][i], q["high"][i], q["low"][i], q["close"][i]) and ts % 300 == 0]
    df = pd.DataFrame(rows, columns=["t", "open", "high", "low", "close"])
    df["ts"] = pd.to_datetime(df["t"], unit="s", utc=True)
    return df


def td_bars(symbol: str) -> pd.DataFrame:
    if not TD_KEY:
        raise RuntimeError("bez TWELVEDATA_API_KEY")
    d = _get_json("https://api.twelvedata.com/time_series?" + urllib.parse.urlencode(
        {"symbol": symbol, "interval": "5min", "outputsize": 400, "timezone": "UTC", "order": "ASC"}),
        {"Authorization": f"apikey {TD_KEY}"})
    if d.get("status") == "error":
        raise RuntimeError(d.get("message"))
    df = pd.DataFrame(d["values"])
    df["ts"] = pd.to_datetime(df["datetime"], utc=True)
    for c in ("open", "high", "low", "close"):
        df[c] = df[c].astype(float)
    return df


def fetch(key: str) -> tuple[str, pd.DataFrame]:
    errs = []
    for src, sym in SOURCES[key]:
        try:
            df = (yahoo_bars if src == "yahoo" else td_bars)(sym)
            if len(df):
                return src, df
        except Exception as e:  # noqa: BLE001 — zkus další zdroj
            errs.append(f"{src}:{str(e)[:80]}")
    raise RuntimeError("; ".join(errs))


def static_events(today: date) -> list[str]:
    try:
        ev = edge_stats.load_events(MACRO)
    except OSError:
        return []
    return sorted(k for k, ds in ev.items() if today in ds)


def calendar_events() -> list[str]:
    """Dnešní high-impact události z výhledu dashboardu (pokrývá i data mimo statický seznam)."""
    try:
        d = _get_json(f"{BASE}/api/bias/outlook?ticker=NQ")
    except Exception:  # noqa: BLE001
        return []
    found = set()
    for e in d.get("events") or []:
        t = (e.get("title") or "").lower()
        for k, words in EVENT_WORDS.items():
            if any(w in t for w in words):
                found.add(k)
    return sorted(found)


def quiet(now_et: datetime) -> bool:
    """Víkendové okno (shodné s weekend_switch.sh) + mimo obchodní den (16:35–19:55 ET)."""
    dow, hm = now_et.isoweekday(), now_et.hour * 100 + now_et.minute
    weekend = dow == 6 or (dow == 5 and hm >= 1730) or (dow == 7 and hm < 1600)
    return weekend or 1635 <= hm < 1955


def build(key: str, now: datetime, events_cal: list[str]) -> dict:
    stats = json.loads((STATS_OUT / "stats-src" / f"{key}.json").read_text(encoding="utf-8"))
    edge = stats.get("edge")
    if not edge:
        raise RuntimeError("chybí blok edge (spusť compute_stats.py)")
    src, bars = fetch(key)
    st_today = (now.astimezone(ET) + pd.Timedelta(hours=6)).date() if now.astimezone(ET).hour >= 18 else now.astimezone(ET).date()
    events = sorted(set(static_events(st_today)) | set(events_cal))
    scale = None if src == "yahoo" or key == "gold" else edge["meta"].get("ref_price")
    state = edge_stats.live_state(bars, edge, now, events, price_scale=scale)
    return {"meta": {"instrument": key.upper(), "to": state["date"], "updated": now.isoformat(timespec="seconds"),
                     "src": src, "stats_to": edge["meta"].get("to"), "stats_from": edge["meta"].get("from"),
                     "days": edge["meta"].get("days"), "rth_et": edge["meta"].get("rth_et"),
                     "unit": stats.get("meta", {}).get("unit")},
            **state}


def push(key: str, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
    req = urllib.request.Request(f"{BASE}/api/marketstats/live/{key}", data=body, method="PUT",
                                 headers={"Content-Type": "application/json", "X-Internal-Token": TOKEN, "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()


def run_once(keys: list[str], dry: bool = False) -> None:
    now = datetime.now(timezone.utc)
    cal = calendar_events()
    for k in keys:
        try:
            p = build(k, now, cal)
            if dry:
                print(json.dumps(p, ensure_ascii=False)[:1500])
            else:
                push(k, p)
            print(f"{now:%H:%M} {k}: {p['meta']['src']} {p.get('phase')} "
                  f"{(p.get('range') or {}).get('so_far_pts')} b.", flush=True)
        except Exception as e:  # noqa: BLE001 — jeden instrument nesmí shodit ostatní
            print(f"{now:%H:%M} {k}: CHYBA {str(e)[:200]}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="*")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--dry", action="store_true", help="jen vypiš, nic neposílej")
    a = ap.parse_args()
    keys = a.keys or list(SOURCES)
    if not TOKEN and not a.dry:
        sys.exit("Chybí TRADEZER_TOKEN")
    while True:
        if a.dry or not quiet(datetime.now(ET)):
            run_once(keys, a.dry)
        if not a.loop:
            break
        time.sleep(120)


if __name__ == "__main__":
    main()
