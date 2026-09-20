"""Discovery mode — momentum/relative-volume screener nad univerzem malých/středních
firem (<$50B), krátkodobá spekulace. ZDARMA (Yahoo chart API v8). Výstup = statické
JSON `web/public/discovery.json` (stejný vzor jako /stats, /orb — bez backendu/DB).

Filozofie: „rozcestník, ne rozhodovadlo" — vyhazuje kandidáty + DŮKAZY (momentum,
relativní objem, vzdálenost od 52w high, poloha vůči SMA), NE predikce/verdikt.

Spuštění:
    py data/discovery_scan.py                 # jen zapíše web/public/discovery.json
    py data/discovery_scan.py --push          # + pushne na /api/discovery/ingest (Spark cron)

Env (volitelné):
    FINNHUB_API_KEY   — market-cap filtr (<$50B) + earnings katalyzátor (zdarma finnhub.io)
    TRADEZER_TOKEN    — X-Internal-Token pro --push (stejný jako predictor)
    TRADEZER_BASE_URL — cíl pushe (default https://tradezer.app)

Pozn.: Yahoo blokuje datacentra → běžet z rezidenční IP (Martyho PC / Spark), NE
z GitHub Actions runneru (429). Univerzum je editovatelné (UNIVERSE níže).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "web" / "public" / "discovery.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")

FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "").strip()
MAX_MARKET_CAP = 50_000_000_000.0   # <$50B (small/mid-cap univerzum)
CATALYST_TOP_N = 45                 # kolik top-skóre jmen obohatit o earnings (šetří Finnhub kvótu)
EARNINGS_SOON_DAYS = 10             # earnings do X dní = zvýrazněný katalyzátor

# Univerzum: likvidní small/mid-cap + momentum jména napříč sektory (editovatelné).
# Fáze 2: širší pokrytí <$50B; skutečný market-cap filtr přidán ve `_metrics` (guard
# proti přerostlým mega-capům) až dodáme fundamentální feed. Duplicity se deduplikují.
UNIVERSE = [
    # EV / doprava (GOEV odebrán — Canoo Ch.7 bankrot 2025, delistováno)
    "RIVN", "LCID", "CHPT", "BLNK", "EVGO", "NIO", "XPEV", "LI", "LYFT",
    # Clean energy / solar (NOVA odebrán — Sunnova Ch.11 bankrot 2025, delistováno)
    "PLUG", "ENPH", "RUN", "FSLR", "SEDG", "ARRY", "SHLS", "BE", "STEM",
    # Crypto / miners
    "MARA", "RIOT", "CLSK", "HUT", "BITF", "CIFR", "WULF", "IREN", "COIN", "BTBT",
    # Fintech
    "SOFI", "AFRM", "UPST", "HOOD", "PYPL", "LC", "MQ", "DAVE", "OPFI", "BILL",
    # Software / AI
    "PLTR", "U", "PATH", "DOCN", "S", "AI", "SOUN", "BBAI", "GTLB", "SNOW",
    "NET", "DDOG", "CFLT", "FROG", "ESTC", "CRWD", "ZS", "BRZE", "APP", "DUOL",
    # Space / defense / drony
    "ASTS", "RKLB", "ACHR", "JOBY", "LUNR", "RDW", "KTOS", "AVAV", "PL", "SPCE",
    # Quantum / pokročilý compute
    "IONQ", "RGTI", "QBTS", "QUBT", "ARQQ",
    # Jádro / energetika nové generace
    "OKLO", "SMR", "NNE", "CEG", "VST", "TLN", "GEV",
    # Consumer / spekulace
    "DKNG", "RBLX", "CVNA", "CELH", "ELF", "HIMS", "CAVA", "WING", "TOST", "CHWY",
    # Biotech / zdraví (momentum)
    "MRNA", "VKTX", "CRSP", "NTLA", "BEAM", "RXRX", "TEM", "HOOD",
    # Polovodiče / hardware small-mid
    "WOLF", "AMBA", "INDI", "NVTS", "MU", "SMCI", "ARM", "CRDO", "ALAB", "LSCC",
    # Meme / vysoká beta
    "GME", "AMC", "CVNA", "DJT", "RUM", "MSTR",
]


def _fetch_bars(ticker: str) -> tuple[list[float], list[float]] | None:
    """Yahoo denní close+volume za ~1 rok. (closes, volumes) newest-last, nebo None."""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
           f"?range=1y&interval=1d")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode())
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        print(f"  {ticker}: fetch fail {e}")
        return None
    try:
        res = data["chart"]["result"][0]
        q = res["indicators"]["quote"][0]
        closes = [c for c in q["close"] if c is not None]
        vols = [v for v in q["volume"] if v is not None]
    except (KeyError, IndexError, TypeError):
        return None
    if len(closes) < 60 or len(vols) < 21:
        return None
    return closes, vols


def _pct(a: float, b: float) -> float | None:
    return round((a - b) / b * 100, 2) if b else None


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _metrics(closes: list[float], vols: list[float]) -> dict | None:
    if len(closes) < 60:
        return None
    last = closes[-1]
    prev = closes[-2]
    ret_5d = _pct(last, closes[-6]) if len(closes) >= 6 else None
    ret_20d = _pct(last, closes[-21]) if len(closes) >= 21 else None
    hi_52 = max(closes)
    lo_52 = min(closes)
    sma20 = sum(closes[-20:]) / 20
    sma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else None
    avg_vol20 = sum(vols[-21:-1]) / 20 if len(vols) >= 21 else None
    rel_vol = round(vols[-1] / avg_vol20, 2) if avg_vol20 else None
    from_high = _pct(last, hi_52)   # záporné = pod high
    # Kompozitní momentum skóre (0–100), zvýrazní čerstvé momentum + neobvyklý objem
    # blízko 52w high. Heuristika, ne predikce — hlavní hodnota jsou DŮKAZY níže.
    r20 = _clamp((ret_20d or 0) / 30, -1, 1)          # ±30 % = ±1
    r5 = _clamp((ret_5d or 0) / 15, -1, 1)            # ±15 % = ±1
    rv = _clamp(((rel_vol or 1) - 1) / 2, 0, 1)       # 3× objem = 1
    nh = _clamp(1 + (from_high or -100) / 25, 0, 1)   # do 25 % pod high roste k 1
    score = round(100 * (0.40 * (r20 + 1) / 2 + 0.25 * (r5 + 1) / 2
                         + 0.20 * rv + 0.15 * nh), 1)
    return {
        "price": round(last, 2),
        "chg_pct": _pct(last, prev),
        "ret_5d": ret_5d,
        "ret_20d": ret_20d,
        "rel_vol": rel_vol,
        "from_high_pct": from_high,
        "from_low_pct": _pct(last, lo_52),
        "above_sma20": last > sma20,
        "above_sma50": (last > sma50) if sma50 else None,
        "score": score,
    }


# ── Finnhub (free): market cap + earnings katalyzátory ───────────────────────
_last_finnhub = 0.0


def _finnhub_get(path: str, params: dict) -> dict | list | None:
    """Volání Finnhub free API s pacingem ~60 req/min. None při chybě/bez klíče."""
    global _last_finnhub
    if not FINNHUB_KEY:
        return None
    wait = 1.05 - (time.time() - _last_finnhub)
    if wait > 0:
        time.sleep(wait)
    _last_finnhub = time.time()
    q = urllib.parse.urlencode({**params, "token": FINNHUB_KEY})
    url = f"https://finnhub.io/api/v1{path}?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        print(f"  finnhub {path}: {e}")
        return None


def _market_cap(ticker: str) -> float | None:
    """Market cap v USD (Finnhub vrací v milionech), nebo None."""
    data = _finnhub_get("/stock/profile2", {"symbol": ticker})
    if isinstance(data, dict) and data.get("marketCapitalization"):
        return float(data["marketCapitalization"]) * 1_000_000
    return None


def _earnings(ticker: str) -> dict:
    """Nejbližší budoucí earnings + poslední EPS surprise. Prázdný dict když nedostupné."""
    out: dict = {}
    today = dt.date.today()
    cal = _finnhub_get("/calendar/earnings", {
        "symbol": ticker,
        "from": today.isoformat(),
        "to": (today + dt.timedelta(days=90)).isoformat(),
    })
    if isinstance(cal, dict):
        dates = sorted(e["date"] for e in cal.get("earningsCalendar", []) if e.get("date"))
        future = [d for d in dates if d >= today.isoformat()]
        if future:
            out["earnings_date"] = future[0]
            out["days_to_earnings"] = (dt.date.fromisoformat(future[0]) - today).days
    hist = _finnhub_get("/stock/earnings", {"symbol": ticker, "limit": 1})
    if isinstance(hist, list) and hist:
        sp = hist[0].get("surprisePercent")
        if sp is not None:
            out["last_surprise_pct"] = round(float(sp), 1)
    return out


def _scan(tickers: list[str]) -> list[dict]:
    """Yahoo momentum pass přes celé univerzum → seřazené items se score."""
    items = []
    for t in tickers:
        bars = _fetch_bars(t)
        if not bars:
            continue
        m = _metrics(*bars)
        if m:
            items.append({"ticker": t, **m})
        time.sleep(0.3)  # jemně vůči Yahoo
    items.sort(key=lambda x: x["score"], reverse=True)
    return items


def _enrich(items: list[dict]) -> tuple[list[dict], int]:
    """Finnhub: market-cap filtr (<$50B) na všech + earnings na top-N. Vrací (items, dropped)."""
    if not FINNHUB_KEY:
        return items, 0
    print(f"Finnhub: market cap {len(items)} jmen (pacing ~1/s)…")
    kept, dropped = [], 0
    for it in items:
        cap = _market_cap(it["ticker"])
        it["market_cap"] = cap
        if cap is not None and cap > MAX_MARKET_CAP:
            dropped += 1
            continue  # přerostlý mega-cap → mimo univerzum
        kept.append(it)
    top = kept[:CATALYST_TOP_N]
    print(f"Finnhub: earnings pro top {len(top)}…")
    for it in top:
        it.update(_earnings(it["ticker"]))
    return kept, dropped


def _push(base: str, payload: dict) -> None:
    token = os.environ.get("TRADEZER_TOKEN", "").strip()
    if not token:
        print("  --push přeskočen: chybí TRADEZER_TOKEN")
        return
    url = base.rstrip("/") + "/api/discovery/ingest"
    body = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json", "X-Internal-Token": token, "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"  push -> {url}: {r.status} {r.read().decode()[:120]}")
    except urllib.error.HTTPError as e:
        print(f"  push FAIL {e.code}: {e.read().decode()[:200]}")
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"  push FAIL: {e}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Discovery momentum screener")
    ap.add_argument("--push", action="store_true", help="pushni na /api/discovery/ingest")
    ap.add_argument("--base", default=os.environ.get("TRADEZER_BASE_URL", "https://tradezer.app"))
    ap.add_argument("--no-file", action="store_true", help="nezapisuj lokální discovery.json")
    args = ap.parse_args()

    tickers = sorted(set(UNIVERSE))
    print(f"Discovery scan: {len(tickers)} tickerů (Yahoo)…")
    items = _scan(tickers)
    items, dropped = _enrich(items)

    out = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "universe_size": len(tickers),
        "scanned": len(items),
        "catalysts": bool(FINNHUB_KEY),
        "note": "Momentum/relativní objem nad small/mid-cap univerzem (<$50B). Rozcestník, "
                "ne investiční doporučení. Data Yahoo (denní) + Finnhub (katalyzátory), zdarma.",
        "items": items,
    }
    if dropped:
        print(f"  market-cap filtr vyhodil {dropped} jmen >$50B")
    if not args.no_file:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"-> {OUT} ({len(items)}/{len(tickers)} ok)")
    if args.push:
        _push(args.base, out)


if __name__ == "__main__":
    main()
