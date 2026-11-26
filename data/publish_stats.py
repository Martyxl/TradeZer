#!/usr/bin/env python3
"""Publikuje spočítané market statistiky (výstup `compute_stats.py`) na backend — bez GitHubu.

Čte <out>/stats-src/<key>.json a <out>/orb/<key>.json a nahraje je přes
PUT /api/marketstats/{stats|orb}/{key}. Web je čte z DB (při chybějícím blobu spadne na statický JSON).

Navíc pošle denní close instrumentů Dashboardu (NQ, ES, YM, zlato, FX) za ~3 roky z Yahoo
(POST /api/investments/prices/history, symboly „MKT:NQ“ …) — pro graf sezónnosti. Chyba tady
nezastaví publikaci statistik.

Env: TRADEZER_TOKEN (povinný, interní API token), TRADEZER_BASE (default https://tradezer.app)
Použití: python3 publish_stats.py [--out DIR]     (default DIR = $STATS_OUT nebo ~/tradezer/stats/out)
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

BASE = os.environ.get("TRADEZER_BASE", "https://tradezer.app").rstrip("/")
TOKEN = os.environ.get("TRADEZER_TOKEN", "").strip()
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TradezerStats/1.0"


def put(kind: str, key: str, payload: dict) -> str:
    body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/api/marketstats/{kind}/{key}", data=body, method="PUT",
        headers={"Content-Type": "application/json", "X-Internal-Token": TOKEN, "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        j = json.loads(r.read().decode())
    return f"{kind}:{key} ok ({j.get('bytes')} B, do {j.get('to')})"


# Instrument Dashboardu → Yahoo symbol (denní data; futures místo indexů, zlato = futures GC).
SEASONAL = {"NQ": "NQ=F", "ES": "ES=F", "YM": "YM=F", "XAUUSD": "GC=F",
            "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "JPY=X"}
SEASONAL_PREFIX = "MKT:"


def seasonal_since(today: date, years: int = 3) -> str:
    """Od kdy posílat: prosinec před nejstarším zobrazeným rokem (základ pro 1. leden)."""
    return f"{today.year - years}-12-01"


def daily_bars(chart: dict, since: str) -> list[dict]:
    """Yahoo chart JSON → [{date, close}] od `since` (datum v UTC, bez prázdných close)."""
    res = chart["chart"]["result"][0]
    closes = (res.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
    out = {}
    for t, c in zip(res.get("timestamp") or [], closes):
        if c is None:
            continue
        d = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")
        if d >= since:
            out[d] = round(float(c), 6)   # u FX bývá víc záznamů na den → poslední vyhrává
    return [{"date": d, "close": c} for d, c in sorted(out.items())]


def publish_seasonal() -> None:
    since = seasonal_since(date.today())
    for key, yh in SEASONAL.items():
        try:
            req = urllib.request.Request(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(yh)}?range=5y&interval=1d",
                headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                bars = daily_bars(json.loads(r.read().decode()), since)
            if not bars:
                print(f"sezónnost {key}: Yahoo nic nevrátil", flush=True)
                continue
            body = json.dumps({"symbol": SEASONAL_PREFIX + key, "bars": bars}).encode()
            req = urllib.request.Request(f"{BASE}/api/investments/prices/history", data=body, method="POST",
                                         headers={"Content-Type": "application/json", "X-Internal-Token": TOKEN,
                                                  "User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                j = json.loads(r.read().decode())
            print(f"sezónnost {key}: {len(bars)} dní od {bars[0]['date']} ({j.get('upserted')} změn)", flush=True)
        except (urllib.error.URLError, ValueError, OSError, KeyError, IndexError, TypeError) as e:
            print(f"sezónnost {key} CHYBA {e}", flush=True)
        time.sleep(1)


def main() -> None:
    if not TOKEN:
        sys.exit("Chybí TRADEZER_TOKEN")
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.environ.get("STATS_OUT") or str(Path.home() / "tradezer" / "stats" / "out"))
    out = Path(ap.parse_args().out)
    failed = 0
    for kind, sub in (("stats", "stats-src"), ("orb", "orb")):
        for f in sorted((out / sub).glob("*.json")):
            try:
                print(put(kind, f.stem, json.loads(f.read_text(encoding="utf-8"))), flush=True)
            except (urllib.error.URLError, ValueError, OSError) as e:
                failed += 1
                print(f"{kind}:{f.stem} CHYBA {e}", flush=True)
    publish_seasonal()
    if failed:
        sys.exit(f"{failed} souborů se nepodařilo publikovat")


if __name__ == "__main__":
    main()
