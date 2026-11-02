"""Historie 5min barů z Twelve Data (placený zdroj) → lokální cache pro statistiky „Edge“.

Proč: vlastní 5min data (Dukascopy do 7/2026 + Yahoo sběr) pokrývají jen ~15 měsíců a Dukascopy
přestalo fungovat. Twelve Data má 5min historii od 2020 — pro indexy ale jen přes ETF proxy
(NQ → QQQ, YM → DIA; futures/indexy TD nemá), zlato přímo XAU/USD (24 h).

ETF obchodují jen v RTH (9:30–16:00 ET) → z TD se berou jen RTH metriky (rozsah, extrémy, trend,
makro dny) v PROCENTECH ceny; body se dopočítají z aktuální ceny NQ/YM. Overnight sessions
(Asia/London) pro NQ/YM jsou jen z vlastních futures dat.

Cache: <raw>/td/<key>-td-m5.csv (timestamp ms UTC, open, high, low, close, volume), inkrementálně.
Když klíč chybí / trial vyprší / TD nejde → cache zůstane a výpočet jede z toho, co je
(+ vlastní data jako záloha; viz edge_stats.build_days).

Použití:  python3 td_history.py [--raw DIR] [klíč ...]      (env TWELVEDATA_API_KEY)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TradezerStats/1.0"
SYMBOLS = {"nq": "QQQ", "ym": "DIA", "gold": "XAU/USD"}
START = {"nq": "2020-02-10", "ym": "2020-02-10", "gold": "2020-03-16"}   # nejstarší 5min data v TD
CHUNK_DAYS = {"nq": 60, "ym": 60, "gold": 16}                           # < 5000 barů na dotaz


def _td(params: dict, key: str) -> dict:
    url = "https://api.twelvedata.com/time_series?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Authorization": f"apikey {key}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except ValueError:
            return {"status": "error", "message": f"HTTP {e.code}"}


def parse_values(values: list[dict]) -> list[tuple]:
    out = []
    for v in values or []:
        try:
            ts = datetime.strptime(v["datetime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            out.append((int(ts.timestamp() * 1000), float(v["open"]), float(v["high"]), float(v["low"]),
                        float(v["close"]), float(v.get("volume") or 0)))
        except (KeyError, ValueError):
            continue
    return out


def path_for(raw: Path, key: str) -> Path:
    return raw / "td" / f"{key}-td-m5.csv"


def load_cache(path: Path) -> dict[int, tuple]:
    have: dict[int, tuple] = {}
    if path.exists():
        with path.open(newline="") as f:
            for r in csv.DictReader(f):
                ts = int(r["timestamp"])
                have[ts] = (ts, float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]),
                            float(r["volume"] or 0))
    return have


def save_cache(path: Path, have: dict[int, tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for ts in sorted(have):
            w.writerow(have[ts])
    tmp.replace(path)


def update(key: str, raw: Path, api_key: str, now: datetime | None = None) -> tuple[int, int]:
    """Dotáhne chybějící bary od konce cache (nebo od START) do včerejška. Vrací (celkem, nových)."""
    now = now or datetime.now(timezone.utc)
    path = path_for(raw, key)
    have = load_cache(path)
    before = len(have)
    start = (datetime.fromtimestamp(max(have) / 1000, timezone.utc) - timedelta(days=2)) if have \
        else datetime.fromisoformat(START[key]).replace(tzinfo=timezone.utc)
    end = now.replace(hour=0, minute=0, second=0, microsecond=0)   # jen uzavřené dny
    cur, errors = start, 0
    while cur < end:
        nxt = min(cur + timedelta(days=CHUNK_DAYS[key]), end)
        d = _td({"symbol": SYMBOLS[key], "interval": "5min", "timezone": "UTC", "order": "ASC",
                 "outputsize": 5000, "start_date": cur.strftime("%Y-%m-%d %H:%M:%S"),
                 "end_date": nxt.strftime("%Y-%m-%d %H:%M:%S")}, api_key)
        if d.get("status") == "error":
            msg = str(d.get("message", ""))
            if "No data is available" not in msg:      # prázdné okno (svátky) není chyba
                errors += 1
                print(f"  {key} {cur:%Y-%m-%d}: {msg[:120]}", flush=True)
                if errors >= 3:
                    break
        else:
            for row in parse_values(d.get("values")):
                have[row[0]] = row
        cur = nxt
        time.sleep(0.3)
    if len(have) != before:
        save_cache(path, have)
    return len(have), len(have) - before


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="*")
    ap.add_argument("--raw", default=str(Path(__file__).parent / "raw"))
    a = ap.parse_args()
    api_key = os.environ.get("TWELVEDATA_API_KEY", "").strip()
    if not api_key:
        print("TWELVEDATA_API_KEY chybí → cache se neaktualizuje (výpočet pojede z toho, co je)")
        return
    for k in a.keys or list(SYMBOLS):
        if k not in SYMBOLS:
            sys.exit(f"Neznámý klíč {k}")
        total, new = update(k, Path(a.raw), api_key)
        print(f"{k} ({SYMBOLS[k]}): celkem {total} barů, nových {new}", flush=True)


if __name__ == "__main__":
    main()
