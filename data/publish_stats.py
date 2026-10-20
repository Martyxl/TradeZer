#!/usr/bin/env python3
"""Publikuje spočítané market statistiky (výstup `compute_stats.py`) na backend — bez GitHubu.

Čte <out>/stats-src/<key>.json a <out>/orb/<key>.json a nahraje je přes
PUT /api/marketstats/{stats|orb}/{key}. Web je čte z DB (při chybějícím blobu spadne na statický JSON).

Env: TRADEZER_TOKEN (povinný, interní API token), TRADEZER_BASE (default https://tradezer.app)
Použití: python3 publish_stats.py [--out DIR]     (default DIR = $STATS_OUT nebo ~/tradezer/stats/out)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
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
    if failed:
        sys.exit(f"{failed} souborů se nepodařilo publikovat")


if __name__ == "__main__":
    main()
