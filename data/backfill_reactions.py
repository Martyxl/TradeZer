"""Backfill market reactions z lokálních Dukascopy 5m dat do produkčního API.

Pro každou zprávu (NQ, XAUUSD) najde cenu v čase publikace a +5m/10m/30m/1h/1d,
spočítá procentní pohyby a pošle na POST /api/backfill/reactions.
realized_direction počítá server z neutral_threshold tickeru.

Použití: py backfill_reactions.py [--dry-run] [--limit 100]
"""
from __future__ import annotations

import argparse
import bisect
import glob
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

API = "https://tradezer.app"
TOKEN = os.environ.get("TRADEZER_TOKEN", "tradezer-secret-2026")
RAW = Path(__file__).parent / "raw"

TICKER_DATA = {
    "NQ": "usatechidxusd-m5-*.csv",
    "XAUUSD": "xauusd-m5-*.csv",
}
# thresholds jen pro liquidity_grab detekci v price_series (realized počítá server)
TICKER_THRESHOLD = {"NQ": 0.003, "XAUUSD": 0.002}


def http_json(path: str, method: str = "GET", body: dict | None = None) -> dict | list:
    req = urllib.request.Request(
        API + path,
        method=method,
        headers={"X-Internal-Token": TOKEN, "Content-Type": "application/json"},
        data=json.dumps(body).encode() if body else None,
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def load_bars(pattern: str) -> tuple[list[int], list[float]]:
    files = sorted(glob.glob(str(RAW / pattern)))
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    df = df.drop_duplicates(subset="timestamp").sort_values("timestamp")
    return df["timestamp"].tolist(), df["close"].tolist()


def close_at(ts_ms: list[int], closes: list[float], when: datetime, tolerance_min: int = 20) -> float | None:
    """Close posledního baru <= when (bar timestamp = open time, 5m bar ~ when-5min)."""
    target = int(when.timestamp() * 1000)
    i = bisect.bisect_right(ts_ms, target) - 1
    if i < 0:
        return None
    if target - ts_ms[i] > tolerance_min * 60_000:
        return None  # díra v datech (víkend / výpadek)
    return closes[i]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()

    for symbol, pattern in TICKER_DATA.items():
        ts_ms, closes = load_bars(pattern)
        data_start = datetime.fromtimestamp(ts_ms[0] / 1000, tz=timezone.utc)
        data_end = datetime.fromtimestamp(ts_ms[-1] / 1000, tz=timezone.utc)
        print(f"== {symbol}: {len(ts_ms)} barů ({data_start:%Y-%m-%d} → {data_end:%Y-%m-%d})")

        news = http_json(f"/api/news?ticker={symbol}&limit={args.limit}")
        records = []
        skipped = 0
        for item in news:
            t = datetime.fromisoformat(item["published_at"]).replace(tzinfo=timezone.utc)
            if t < data_start or t > data_end:
                skipped += 1
                continue
            at = close_at(ts_ms, closes, t)
            if at is None:
                skipped += 1
                continue

            def pct(when: datetime, tol: int = 20) -> float | None:
                p = close_at(ts_ms, closes, when, tol)
                return round((p - at) / at, 6) if p is not None else None

            p5, p10 = pct(t + timedelta(minutes=5), 10), pct(t + timedelta(minutes=10), 10)
            p30 = pct(t + timedelta(minutes=30))
            p1h = pct(t + timedelta(hours=1))
            p1d = pct(t + timedelta(days=1), 90)

            thr = TICKER_THRESHOLD[symbol]
            def d(p):
                return 0 if p is None or abs(p) < thr * 0.4 else (1 if p > 0 else -1)
            grab = d(p5) != 0 and d(p30) != 0 and d(p5) != d(p30)

            records.append({
                "news_id": item["id"],
                "ticker": symbol,
                "price_at_news": at,
                "price_30m": close_at(ts_ms, closes, t + timedelta(minutes=30)),
                "price_1h": close_at(ts_ms, closes, t + timedelta(hours=1)),
                "price_1d": close_at(ts_ms, closes, t + timedelta(days=1), 90),
                "pct_30m": p30,
                "pct_1h": p1h,
                "pct_1d": p1d,
                "price_series": {
                    "pct_5m": round(p5 * 100, 5) if p5 is not None else None,
                    "pct_10m": round(p10 * 100, 5) if p10 is not None else None,
                    "pct_30m": round(p30 * 100, 5) if p30 is not None else None,
                    "pct_1h": round(p1h * 100, 5) if p1h is not None else None,
                    "liquidity_grab": grab,
                    "initial_dir": "up" if d(p5) > 0 else ("down" if d(p5) < 0 else "flat"),
                    "source": "dukascopy-backfill",
                },
            })

        print(f"   zpráv: {len(news)}, k odeslání: {len(records)}, mimo data: {skipped}")
        if args.dry_run or not records:
            for r in records[:5]:
                print("   ", r["news_id"], r["pct_30m"])
            continue

        for i in range(0, len(records), 200):
            batch = records[i:i + 200]
            result = http_json("/api/backfill/reactions", "POST", {"records": batch})
            print(f"   batch {i // 200 + 1}: {result}")


if __name__ == "__main__":
    main()
