"""Portfolio quotes scan — stáhne živé ceny držených tickerů + FX kurzy z Yahoo
a pushne je na backend (investorský deník používá pro aktuální hodnotu portfolia).

Yahoo blokuje datacentra → BĚŽET Z REZIDENČNÍ IP (Martyho PC / Spark), stejně jako
discovery/gamma/smart_money skeny. Backend čte držené symboly přes /symbols.

Env:
    TRADEZER_TOKEN    — X-Internal-Token (stejný interní token)
    TRADEZER_BASE_URL — cíl (default https://tradezer.app)
Spuštění:
    TRADEZER_TOKEN=... py data/portfolio_quotes_scan.py --push
    (--loop N → opakuje každých N minut; default jednorázově)
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TradezerQuotes/1.0"
BASE_FX = "CZK"  # do jaké měny se portfolio přepočítává (musí sedět s portfolio?base=)


def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except (urllib.error.URLError, TimeoutError, ValueError, urllib.error.HTTPError) as e:
        print(f"  fetch fail {url[:60]}: {e}")
        return None


# Mapování suffixů na Yahoo burzovní kódy (uložený symbol zůstává původní).
_YH_SUFFIX = {".NV": ".AS", ".NL": ".AS", ".SW": ".SW", ".LN": ".L", ".UK": ".L", ".GB": ".L"}
# Přímé aliasy pro symboly, co přišly bez burzovního suffixu (XTB strhl .DE apod.).
_YH_ALIAS = {"KWBE": "KWBE.DE"}  # KraneShares China Internet UCITS (Xetra, EUR)


def _yahoo_sym(symbol: str) -> str:
    s = symbol.upper()
    if s in _YH_ALIAS:
        return _YH_ALIAS[s]
    if s.endswith(".US"):
        return s[:-3]  # US akcie na Yahoo bez suffixu
    for suf, rep in _YH_SUFFIX.items():
        if s.endswith(suf):
            return s[:-len(suf)] + rep
    return s


def _fetch(symbol: str) -> tuple[dict | None, list[dict]]:
    """Jedním Yahoo dotazem (range=2y) vrátí (quote, historii denních close).
    quote = aktuální cena + měna + 52T z meta; history = [{date, close}] pro křivku."""
    data = _get_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{_yahoo_sym(symbol)}?range=2y&interval=1d")
    try:
        res = data["chart"]["result"][0]
        meta = res["meta"]
        price = meta.get("regularMarketPrice")
        q = None
        if price is not None:
            q = {"symbol": symbol.upper(), "price": float(price),
                 "currency": meta.get("currency"), "source": "yahoo"}
            if meta.get("fiftyTwoWeekHigh") is not None:
                q["high_52w"] = float(meta["fiftyTwoWeekHigh"])
            if meta.get("fiftyTwoWeekLow") is not None:
                q["low_52w"] = float(meta["fiftyTwoWeekLow"])
        ts = res.get("timestamp") or []
        closes = (res.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
        bars = [{"date": time.strftime("%Y-%m-%d", time.gmtime(t)), "close": float(c)}
                for t, c in zip(ts, closes) if c is not None]
        return q, bars
    except (KeyError, IndexError, TypeError):
        return None, []


def held_symbols(base: str, token: str) -> tuple[list[str], list[str]]:
    req = urllib.request.Request(f"{base}/api/investments/symbols",
                                 headers={"User-Agent": UA, "X-Internal-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode())
            return d.get("symbols", []), d.get("currencies", [])
    except urllib.error.HTTPError as e:
        print(f"  /symbols HTTP {e.code}")
        return [], []
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"  /symbols fail {e}")
        return [], []


def push(base: str, token: str, quotes: list[dict]) -> None:
    body = json.dumps({"quotes": quotes}).encode()
    req = urllib.request.Request(f"{base}/api/investments/quotes/ingest", data=body,
                                 method="POST", headers={"Content-Type": "application/json",
                                 "X-Internal-Token": token, "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"  push OK: {r.read().decode()[:120]}")
    except urllib.error.HTTPError as e:
        print(f"  push HTTP {e.code}: {e.read().decode()[:120]}")
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"  push fail {e}")


def push_history(base: str, token: str, symbol: str, bars: list[dict]) -> None:
    if not bars:
        return
    body = json.dumps({"symbol": symbol, "bars": bars}).encode()
    req = urllib.request.Request(f"{base}/api/investments/prices/history", data=body,
                                 method="POST", headers={"Content-Type": "application/json",
                                 "X-Internal-Token": token, "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            r.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
        print(f"  history push fail {symbol}: {e}")


def run_once(base: str, token: str) -> None:
    symbols, currencies = held_symbols(base, token)
    print(f"drženo: {len(symbols)} symbolů, měny {currencies}")
    quotes = []
    for s in symbols:
        q, bars = _fetch(s)
        if q:
            quotes.append(q)
            print(f"  {s} = {q['price']} {q['currency']} ({len(bars)} barů hist)")
        push_history(base, token, s.upper(), bars)
        time.sleep(0.3)
    # FX páry pro přepočet do BASE_FX (např. USDCZK, EURCZK) — i jejich historie
    for ccy in currencies:
        if ccy and ccy != BASE_FX:
            fx, fx_bars = _fetch(f"{ccy}{BASE_FX}=X")
            sym = f"{ccy}{BASE_FX}"
            if fx:
                fx["symbol"] = sym
                quotes.append(fx)
                print(f"  {sym} = {fx['price']} ({len(fx_bars)} barů hist)")
            push_history(base, token, sym, fx_bars)
            time.sleep(0.3)
    if quotes:
        push(base, token, quotes)
    else:
        print("  nic k pushnutí (žádné držené symboly nebo ceny)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("TRADEZER_BASE_URL", "https://tradezer.app"))
    ap.add_argument("--loop", type=int, default=0, help="opakuj každých N minut")
    ap.add_argument("--push", action="store_true", help="(ponecháno pro konzistenci; push je vždy)")
    args = ap.parse_args()
    token = os.environ.get("TRADEZER_TOKEN", "").strip()
    if not token:
        sys.exit("Chybí TRADEZER_TOKEN env.")
    base = args.base.rstrip("/")
    while True:
        print(f"[{time.strftime('%H:%M:%S')}] portfolio quotes -> {base}")
        run_once(base, token)
        if args.loop <= 0:
            break
        time.sleep(args.loop * 60)


if __name__ == "__main__":
    main()
