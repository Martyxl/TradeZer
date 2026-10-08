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


def _fetch(symbol: str, rng: str = "2y") -> tuple[dict | None, list[dict]]:
    """Jedním Yahoo dotazem vrátí (quote, historii denních close) za období `rng`.
    quote = aktuální cena + měna + 52T z meta; history = [{date, close}] pro křivku."""
    data = _get_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{_yahoo_sym(symbol)}?range={rng}&interval=1d")
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


def push_history(base: str, token: str, symbol: str, bars: list[dict]) -> bool:
    if not bars:
        return False
    body = json.dumps({"symbol": symbol, "bars": bars}).encode()
    req = urllib.request.Request(f"{base}/api/investments/prices/history", data=body,
                                 method="POST", headers={"Content-Type": "application/json",
                                 "X-Internal-Token": token, "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            r.read()
        return True
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
        print(f"  history push fail {symbol}: {e}")
        return False


# Historie se NEposílá každou hodinu (dřív 2 roky × ~22 symbolů × 24×/den = tisíce zbytečných
# volání, která žrala limity Vercelu i čas Neonu). Plán: nový symbol → 2y jednou; jinak jednou
# denně poslední měsíc; ostatní hodiny jen živá cena (range=5d, bez historie).
HIST_STATE = os.environ.get("PORTFOLIO_HIST_STATE",
                            os.path.join(os.path.dirname(os.path.abspath(__file__)), "portfolio_hist_state.json"))


def _load_state() -> dict:
    try:
        with open(HIST_STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_state(st: dict) -> None:
    try:
        with open(HIST_STATE, "w", encoding="utf-8") as f:
            json.dump(st, f)
    except OSError as e:
        print(f"  stav historie nezapsán: {e}")


def history_plan(state: dict, symbol: str, today: str) -> tuple[str, bool]:
    """(Yahoo range, poslat historii?) pro symbol."""
    last = state.get(symbol)
    if last is None:
        return "2y", True
    if last != today:
        return "1mo", True
    return "5d", False


def run_once(base: str, token: str) -> None:
    symbols, currencies = held_symbols(base, token)
    print(f"drženo: {len(symbols)} symbolů, měny {currencies}")
    quotes = []
    state, today = _load_state(), time.strftime("%Y-%m-%d")
    pushed = 0

    def handle(sym: str, yh: str) -> dict | None:
        nonlocal pushed
        rng, want_hist = history_plan(state, sym, today)
        q, bars = _fetch(yh, rng)
        if want_hist and push_history(base, token, sym, bars):
            state[sym] = today
            pushed += 1
        print(f"  {sym} = {q['price'] if q else None} ({rng}, historie {'poslána' if want_hist else 'přeskočena'})")
        return q

    for s in symbols:
        q = handle(s.upper(), s)
        if q:
            quotes.append(q)
        time.sleep(0.3)
    # FX páry pro přepočet do BASE_FX (např. USDCZK, EURCZK) — i jejich historie
    for ccy in currencies:
        if ccy and ccy != BASE_FX:
            sym = f"{ccy}{BASE_FX}"
            fx = handle(sym, f"{sym}=X")
            if fx:
                fx["symbol"] = sym
                quotes.append(fx)
            time.sleep(0.3)
    if pushed:
        _save_state(state)
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
