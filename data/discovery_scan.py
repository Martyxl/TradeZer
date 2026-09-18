"""Discovery mode — momentum/relative-volume screener nad univerzem malých/středních
firem (<$50B), krátkodobá spekulace. ZDARMA (Yahoo chart API v8). Výstup = statické
JSON `web/public/discovery.json` (stejný vzor jako /stats, /orb — bez backendu/DB).

Filozofie: „rozcestník, ne rozhodovadlo" — vyhazuje kandidáty + DŮKAZY (momentum,
relativní objem, vzdálenost od 52w high, poloha vůči SMA), NE predikce/verdikt.

Spuštění:  py data/discovery_scan.py
Pozn.: Yahoo blokuje datacentra → běžet z rezidenční IP (Martyho PC / Spark), NE
z GitHub Actions runneru (429). Univerzum je editovatelné (UNIVERSE níže).
"""
from __future__ import annotations

import datetime as dt
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "web" / "public" / "discovery.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")

# Startovní univerzum: likvidní small/mid-cap + momentum jména (editovatelné/rozšiřitelné).
# V2: nahradit skutečným screenerem <$50B z feedu (market-cap filtr).
UNIVERSE = [
    "SOFI", "RIVN", "LCID", "CHPT", "PLUG", "MARA", "RIOT", "CLSK", "HUT", "AFRM",
    "UPST", "HOOD", "DKNG", "RBLX", "U", "PATH", "DOCN", "S", "CVNA", "WOLF",
    "ENPH", "RUN", "FSLR", "ASTS", "RKLB", "ACHR", "JOBY", "IONQ", "RGTI", "OKLO",
    "SMR", "LUNR", "SOUN", "BBAI", "HIMS", "CELH", "ELF", "DUOL", "AI", "AFRM",
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


def main() -> None:
    tickers = sorted(set(UNIVERSE))
    print(f"Discovery scan: {len(tickers)} tickerů (Yahoo)…")
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
    out = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "universe_size": len(tickers),
        "scanned": len(items),
        "note": "Momentum/relativní objem nad small/mid-cap univerzem. Rozcestník, ne "
                "investiční doporučení. Data Yahoo (denní), zdarma.",
        "items": items,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"-> {OUT} ({len(items)}/{len(tickers)} ok)")


if __name__ == "__main__":
    main()
