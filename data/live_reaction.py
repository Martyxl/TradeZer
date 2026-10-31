#!/usr/bin/env python3
"""Živá reakce trhu na vydaná makro data (Twelve Data 1min) → dashboard „Dnešní výhled“.

Od 2 min před vydáním do 65 min po něm každých ~20 s stáhne 1min svíčky a spočítá pohyb od ceny
těsně PŘED vydáním (body 1/5/15/30/60 min + poslední cena). Forex/zlato/BTC přímo, indexové
futures přes ETF (ES→SPY, NQ→QQQ, YM→DIA, vč. pre/after-market 4:00–20:00 New York).
Kalendář („co právě sledovat“) bere z backendu, výsledek pushne na /api/bias/outlook/live/ingest.
Jen stdlib. Běh (Spark): TWELVEDATA_API_KEY=… TRADEZER_TOKEN=… python3 live_reaction.py --loop
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

BASE = os.environ.get("TRADEZER_BASE_URL", "https://tradezer.app").rstrip("/")
TOKEN = os.environ.get("TRADEZER_TOKEN", "")
TD_KEY = os.environ.get("TWELVEDATA_API_KEY", "")
NY = ZoneInfo("America/New_York")

TD_SYM = {"EURUSD": "EUR/USD", "GBPUSD": "GBP/USD", "USDJPY": "USD/JPY", "XAUUSD": "XAU/USD",
          "BTCUSD": "BTC/USD", "ES": "SPY", "NQ": "QQQ", "YM": "DIA"}
PROXY = {"ES": "SPY", "NQ": "QQQ", "YM": "DIA"}
POINTS = (1, 5, 15, 30, 60)
WINDOW_MIN = 65


def log(*a):
    print(datetime.now().strftime("%H:%M:%S"), *a, flush=True)


def _get(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def due_events():
    return _get(f"{BASE}/api/bias/outlook/live/due", {"X-Internal-Token": TOKEN}).get("events") or []


def bars(ticker, start, end):
    """[(start_epoch, close)] 1min, UTC. ETF proxy s pre/after-market."""
    q = {"symbol": TD_SYM[ticker], "interval": "1min", "timezone": "UTC", "order": "ASC", "outputsize": 5000,
         "start_date": start.strftime("%Y-%m-%d %H:%M:%S"), "end_date": end.strftime("%Y-%m-%d %H:%M:%S")}
    if ticker in PROXY:
        q["prepost"] = "true"
    d = _get("https://api.twelvedata.com/time_series?" + urllib.parse.urlencode(q),
             {"Authorization": f"apikey {TD_KEY}"})
    out = []
    for b in d.get("values") or []:
        t = datetime.strptime(b["datetime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
        out.append((t, float(b["close"])))
    return out


def _close_before(bs, target, tol_min):
    best = None
    for t, c in bs:
        if t + 60 <= target and target - (t + 60) <= tol_min * 60:
            best = c
    return best


def measure(bs, ev, now, proxy):
    """Pohyb od ceny před vydáním. None = cena před vydáním chybí (trh zavřený)."""
    e, n = ev.timestamp(), now.timestamp()
    p0 = _close_before(bs, e, 15 if proxy else 5)
    if not p0:
        return None
    pts = {}
    for m in POINTS:
        if n >= e + m * 60:
            p = _close_before(bs, e + m * 60, 3 if not proxy else 5)
            if p is not None:
                pts[str(m)] = round((p / p0 - 1) * 100, 5)
    after = [(t, c) for t, c in bs if t >= e and t <= n]
    last_pct = last_at = None
    if after:
        t, c = after[-1]
        last_pct = round((c / p0 - 1) * 100, 5)
        last_at = datetime.fromtimestamp(min(t + 60, n), tz=timezone.utc).isoformat()
    return {"p0": p0, "points": pts, "last_pct": last_pct, "last_at": last_at}


def tick(now=None):
    now = now or datetime.now(timezone.utc)
    events = due_events()
    started = [e for e in events if datetime.fromisoformat(e["time_utc"]) <= now]
    if not started:
        return len(events), 0
    first = min(datetime.fromisoformat(e["time_utc"]) for e in started)
    items = []
    for tk in TD_SYM:
        try:
            bs = bars(tk, first - timedelta(minutes=20), now + timedelta(minutes=1))
        except Exception as ex:  # noqa: BLE001
            log("TD chyba", tk, str(ex)[:120])
            continue
        for e in started:
            m = measure(bs, datetime.fromisoformat(e["time_utc"]), now, tk in PROXY)
            if m:
                items.append({"event_title": e["title"], "event_time_utc": e["time_utc"], "ticker": tk,
                              "proxy": PROXY.get(tk), **m})
    if items:
        req = urllib.request.Request(f"{BASE}/api/bias/outlook/live/ingest", method="POST",
                                     data=json.dumps({"items": items}).encode(),
                                     headers={"Content-Type": "application/json", "X-Internal-Token": TOKEN})
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
    return len(events), len(items)


def weekend(now):
    """Pá 17:00 → ne 17:00 New York: žádná makra, nevolat backend ani Twelve Data."""
    ny = now.astimezone(NY)
    return ny.weekday() == 5 or (ny.weekday() == 4 and ny.hour >= 17) or (ny.weekday() == 6 and ny.hour < 17)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", action="store_true")
    a = ap.parse_args()
    if not (TD_KEY and TOKEN):
        sys.exit("Chybí TWELVEDATA_API_KEY nebo TRADEZER_TOKEN")
    while True:
        now = datetime.now(timezone.utc)
        sleep = 60
        if not weekend(now):
            try:
                n_ev, n_items = tick(now)
                if n_ev:
                    sleep = 20
                if n_items:
                    log(f"eventů {n_ev}, zapsáno reakcí {n_items}")
            except Exception as ex:  # noqa: BLE001
                log("chyba", str(ex)[:200])
        if not a.loop:
            break
        time.sleep(sleep)


if __name__ == "__main__":
    main()
