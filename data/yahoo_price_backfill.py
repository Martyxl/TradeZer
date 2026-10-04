#!/usr/bin/env python3
"""Lokální backfill denních cen z Yahoo do Tradezer Valuation.

Obchází mezeru, kde FMP free nedává hlubokou historii pro některé firmy (LLY, MRK,
AVGO, AMGN, VRTX, OGN). Yahoo chart API blokuje datacentra (cloud/CI) → spouštěj
z rezidenční IP (tvé PC) nebo zapoj jako HTTP node do n8n.

Tok: Yahoo chart (10 let, denní, vč. adjClose) → POST /api/valuation/prices/ingest
     (idempotentní upsert) → POST /api/valuation/refresh (recompute+score) → percentil.

Použití:
  py data/yahoo_price_backfill.py                 # default 6 firem bez hluboké historie
  py data/yahoo_price_backfill.py LLY MRK AVGO    # konkrétní tickery
  TRADEZER_BASE=https://tradezer.app TRADEZER_TOKEN=... py data/yahoo_price_backfill.py
"""
from __future__ import annotations
import argparse, json, os, sys, time
import urllib.error
import urllib.parse
import urllib.request

# Windows konzole (cp1250) neumí unicode šipky apod. → vynuť UTF-8 výstup.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

BASE = os.environ.get("TRADEZER_BASE", "https://tradezer.app").rstrip("/")
TOKEN = os.environ.get("TRADEZER_TOKEN", "")
if not TOKEN:
    raise SystemExit("Chybí TRADEZER_TOKEN env (interní API token). Nastav ho a spusť znovu.")
DEFAULT_TICKERS = ["LLY", "MRK", "AVGO", "AMGN", "VRTX", "OGN"]
# Rozsah stahování: plné seedování historie = 10y; denní udržování (Spark) stačí
# krátký (např. 1mo) → rychlé, jen doplní nejnovější bary (ingest je idempotentní).
RANGE = os.environ.get("YH_RANGE", "10y")

_UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")}
_CHART = ("https://query1.finance.yahoo.com/v8/finance/chart/{t}"
          "?range=" + RANGE + "&interval=1d&includeAdjustedClose=true")


def _get(url: str, headers: dict, timeout: int = 45) -> dict:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _post(url: str, payload: dict, headers: dict, timeout: int = 90) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={**headers, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def fetch_universe() -> list[str]:
    """Display tickery z backendu (interní token) — ať backfill pokryje vše."""
    return _get(f"{BASE}/api/valuation/universe", {"X-Internal-Token": TOKEN}, 30).get("tickers", [])


def fetch_yahoo(ticker: str) -> list[dict]:
    """Vrátí denní bary [{date, open, high, low, close, adj_close, volume}] ASC."""
    res = _get(_CHART.format(t=ticker), _UA, 45)["chart"]["result"][0]
    ts = res.get("timestamp") or []
    q = res["indicators"]["quote"][0]
    adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose") or [None] * len(ts)
    bars = []
    for i, t_ in enumerate(ts):
        close = q["close"][i]
        if close is None:
            continue
        bars.append({
            "date": time.strftime("%Y-%m-%d", time.gmtime(t_)),
            "open": q["open"][i], "high": q["high"][i], "low": q["low"][i],
            "close": close, "adj_close": adj[i], "volume": q["volume"][i],
        })
    return bars


def _post_with_retry(url: str, payload: dict, headers: dict, tries: int = 3) -> dict:
    last_exc = None
    for attempt in range(tries):
        try:
            return _post(url, payload, headers, 90)
        except Exception as e:  # noqa: BLE001
            last_exc = e
            time.sleep(2 * (attempt + 1))
    raise last_exc


def post_prices(ticker: str, bars: list[dict]) -> dict:
    """POSTuje bary po dávkách; vrací poslední odpověď + součet vložených."""
    headers = {"X-Internal-Token": TOKEN}
    inserted, last = 0, {}
    for i in range(0, len(bars), 1500):
        chunk = bars[i:i + 1500]
        last = _post_with_retry(f"{BASE}/api/valuation/prices/ingest",
                                {"ticker": ticker, "bars": chunk}, headers)
        inserted += last.get("inserted", 0)
    last["_inserted_total"] = inserted
    return last


def recompute(tickers: list[str]) -> dict:
    qs = urllib.parse.urlencode({"tickers": ",".join(tickers), "with_ingest": "false"})
    return _post(f"{BASE}/api/valuation/refresh?{qs}", {}, {"X-Internal-Token": TOKEN}, 90)


def run_once(tickers: list[str]) -> None:
    ok = []
    for t in tickers:
        try:
            bars = fetch_yahoo(t)
            res = post_prices(t, bars)
            print(f"{t}: Yahoo {len(bars)} baru -> vlozeno {res['_inserted_total']}, "
                  f"v DB celkem {res.get('total_in_db')}")
            ok.append(t)
        except Exception as e:  # noqa: BLE001
            print(f"{t}: CHYBA {e}")
        time.sleep(1)
    if ok:
        rc = recompute(ok)
        st = rc.get("stages", {})
        print(f"Recompute {len(ok)} firem: compute={st.get('compute')} score={st.get('score')}")


def _resolve_tickers(args) -> list[str]:
    if args.tickers:
        return [a.upper() for a in args.tickers]
    # bez tickerů → všechny display firmy z backendu (fallback na default)
    try:
        u = fetch_universe()
        if u:
            return u
    except Exception as e:  # noqa: BLE001
        print(f"universe fetch fail: {e} — fallback na default")
    return DEFAULT_TICKERS


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="*", help="konkrétní tickery; prázdné = všechny display firmy")
    ap.add_argument("--loop", type=int, default=0, help="opakuj každých N minut (Spark: 1440 = denně)")
    args = ap.parse_args()
    while True:
        tickers = _resolve_tickers(args)
        print(f"[{time.strftime('%Y-%m-%d %H:%M')}] backfill {len(tickers)} firem (range={RANGE}) -> {BASE}")
        run_once(tickers)
        if args.loop <= 0:
            break
        time.sleep(args.loop * 60)


if __name__ == "__main__":
    main()
