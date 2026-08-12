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
import os, sys, time
import httpx

BASE = os.environ.get("TRADEZER_BASE", "https://tradezer.app").rstrip("/")
TOKEN = os.environ.get("TRADEZER_TOKEN", "tradezer-secret-2026")
DEFAULT_TICKERS = ["LLY", "MRK", "AVGO", "AMGN", "VRTX", "OGN"]

_UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")}
_CHART = ("https://query1.finance.yahoo.com/v8/finance/chart/{t}"
          "?range=10y&interval=1d&includeAdjustedClose=true")


def fetch_yahoo(ticker: str) -> list[dict]:
    """Vrátí denní bary [{date, open, high, low, close, adj_close, volume}] ASC."""
    r = httpx.get(_CHART.format(t=ticker), headers=_UA, timeout=45)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
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


def post_prices(ticker: str, bars: list[dict]) -> dict:
    """POSTuje bary po dávkách; vrací poslední odpověď + součet vložených."""
    headers = {"X-Internal-Token": TOKEN}
    inserted, last = 0, {}
    for i in range(0, len(bars), 1500):
        chunk = bars[i:i + 1500]
        r = httpx.post(f"{BASE}/api/valuation/prices/ingest",
                       headers=headers, json={"ticker": ticker, "bars": chunk}, timeout=90)
        r.raise_for_status()
        last = r.json()
        inserted += last.get("inserted", 0)
    last["_inserted_total"] = inserted
    return last


def recompute(tickers: list[str]) -> dict:
    r = httpx.post(f"{BASE}/api/valuation/refresh",
                   params={"tickers": ",".join(tickers), "with_ingest": "false"},
                   headers={"X-Internal-Token": TOKEN}, timeout=90)
    r.raise_for_status()
    return r.json()


def main() -> None:
    tickers = [a.upper() for a in sys.argv[1:]] or DEFAULT_TICKERS
    ok = []
    for t in tickers:
        try:
            bars = fetch_yahoo(t)
            res = post_prices(t, bars)
            print(f"{t}: Yahoo {len(bars)} barů → vloženo {res['_inserted_total']}, "
                  f"v DB celkem {res.get('total_in_db')}")
            ok.append(t)
        except Exception as e:  # noqa: BLE001
            print(f"{t}: CHYBA {e}")
        time.sleep(1)
    if ok:
        rc = recompute(ok)
        st = rc.get("stages", {})
        print(f"\nRecompute {ok}:\n  compute={st.get('compute')}\n  score={st.get('score')}")


if __name__ == "__main__":
    main()
