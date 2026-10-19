#!/usr/bin/env python3
"""Sběrač 5m svíček z Yahoo Finance pro market statistiky (Stats/ORB).

Proč: Dukascopy veřejný datafeed vrací 429 (od 10/2026 jen AWS S3 Requester Pays), takže
měsíční stahování přestalo fungovat. Yahoo dává 5m data jen ~60 dní zpět, proto sběrač BĚŽÍ
PRAVIDELNĚ a data NAKUMULUJE do CSV (dedup podle timestampu) — historie tak roste každý den.

Výstup (formát shodný s Dukascopy CSV, který čte compute_stats.load_m5):
  <out>/<key>-m5-yahoo.csv   sloupce: timestamp(ms),open,high,low,close,volume

Použití:  python3 yahoo_m5_collector.py [--out DIR] [--loop MINUT] [klíč ...]
Default klíče: eurusd gbpusd usdjpy (forex). Další: nq gold ym (futures, viz SYMBOLS).
Yahoo chart API blokuje cloud/CI → spouštět z domácí IP (Spark).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TradezerStats/1.0"  # dlouhý chromový UA Yahoo odmítá (429)
SYMBOLS = {
    "eurusd": "EURUSD=X", "gbpusd": "GBPUSD=X", "usdjpy": "USDJPY=X",
    "nq": "NQ=F", "gold": "GC=F", "ym": "YM=F",
}
DEFAULT_KEYS = ["eurusd", "gbpusd", "usdjpy"]


def fetch_m5(symbol: str, rng: str = "60d") -> list[tuple]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={rng}&interval=5m&includePrePost=true"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.loads(r.read().decode())["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    rows = []
    for i, ts in enumerate(res.get("timestamp") or []):
        o, h, lo, c = (q[k][i] for k in ("open", "high", "low", "close"))
        if None in (o, h, lo, c):
            continue
        rows.append((int(ts) * 1000, o, h, lo, c, q["volume"][i] or 0))
    return rows


def merge_into(path: Path, rows: list[tuple]) -> tuple[int, int]:
    """Přidá nové řádky do CSV (dedup + seřazení). Vrací (celkem řádků, nově přidaných)."""
    have: dict[int, tuple] = {}
    if path.exists():
        with path.open(newline="") as f:
            for r in csv.DictReader(f):
                have[int(r["timestamp"])] = (int(r["timestamp"]), float(r["open"]), float(r["high"]),
                                              float(r["low"]), float(r["close"]), float(r["volume"] or 0))
    before = len(have)
    for r in rows:
        have.setdefault(r[0], r)  # starší uložená svíčka má přednost (neměníme historii)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for ts in sorted(have):
            w.writerow(have[ts])
    tmp.replace(path)
    return len(have), len(have) - before


def run_once(out: Path, keys: list[str]) -> int:
    bad = 0
    for k in keys:
        try:
            rows = fetch_m5(SYMBOLS[k])
            total, new = merge_into(out / f"{k}-m5-yahoo.csv", rows)
            print(f"{k}: staženo {len(rows)} svíček, nových {new}, celkem {total}", flush=True)
        except Exception as e:  # noqa: BLE001
            bad += 1
            print(f"{k}: CHYBA {e}", flush=True)
        time.sleep(1.5)
    return bad


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="*")
    ap.add_argument("--out", default=str(Path(__file__).parent / "raw"))
    ap.add_argument("--loop", type=int, default=0, help="opakuj po N minutách (0 = jednou)")
    a = ap.parse_args()
    keys = a.keys or DEFAULT_KEYS
    unknown = [k for k in keys if k not in SYMBOLS]
    if unknown:
        sys.exit(f"Neznámý klíč: {unknown}; známé: {list(SYMBOLS)}")
    out = Path(a.out)
    while True:
        run_once(out, keys)
        if not a.loop:
            break
        time.sleep(a.loop * 60)


if __name__ == "__main__":
    main()
