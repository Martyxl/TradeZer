"""Gamma Exposure (GEX) screener — spočítá dealer gamma z options open interest.

Pro hlavní instrumenty (proxy ETF: NQ→QQQ, ES→SPY, YM→DIA, XAUUSD→GLD, RTY→IWM)
stáhne options chain z Yahoo, spočítá per-strike GEX (Black-Scholes gamma × OI ×
100 × spot² × 1%, dealer konvence call +/put −), z toho:
  • net GEX (gamma index)  → pozitivní = mean-revert/tlumené, negativní = trendové/volatilní
  • gamma flip (zero-gamma level) = spot, kde net GEX mění znaménko
  • call wall = strike s max call gamma (rezistence), put wall = strike s max put gamma (support)
  • profil GEX po strikech kolem spotu (pro mini-graf)

⚠️ MODEL, NE PRAVDA: veřejné OI je snapshot z předchozí noci (statické intraday) a
neidentifikuje dealer vs customer — používáme standardní konvenci. Rozcestník, ne signál.

Spuštění:
    py data/gamma_scan.py               # zapíše web/public/gamma.json
    py data/gamma_scan.py --push        # + pushne na /api/gamma/ingest (Spark cron)

Env (--push): TRADEZER_TOKEN, volitelně TRADEZER_BASE_URL (default https://tradezer.app).
Pozn.: Yahoo blokuje datacentra → běžet z rezidenční IP (Martyho PC / Spark), NE z CI.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "web" / "public" / "gamma.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")

# Instrument → likvidní options proxy (ETF). Index options (^NDX/^SPX) mají na Yahoo
# tenčí pokrytí, ETF je spolehlivější free zdroj.
UNDERLYINGS = {
    "NQ": "QQQ",
    "ES": "SPY",
    "YM": "DIA",
    "XAUUSD": "GLD",
    "RTY": "IWM",
}

RISK_FREE = 0.043          # konstantní r (gamma je na r málo citlivá)
MAX_EXPIRIES = 6           # kolik nejbližších expirací sečíst
MAX_EXPIRY_DAYS = 70       # ignoruj expirace dál než ~10 týdnů (šum)
CONTRACT_MULT = 100        # 1 kontrakt = 100 akcií


def _fetch(url: str) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode())
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        print(f"  fetch fail {e}")
        return None


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def _bs_gamma(S: float, K: float, T: float, iv: float) -> float:
    """Black-Scholes gamma. 0 pro nevalidní vstupy."""
    if S <= 0 or K <= 0 or T <= 0 or iv <= 0:
        return 0.0
    d1 = (math.log(S / K) + (RISK_FREE + 0.5 * iv * iv) * T) / (iv * math.sqrt(T))
    return _norm_pdf(d1) / (S * iv * math.sqrt(T))


def _load_chain(symbol: str) -> tuple[float, list[dict]] | None:
    """Vrátí (spot, contracts) kde contract = {K, oi, iv, T, kind}. None při chybě."""
    base = f"https://query1.finance.yahoo.com/v7/finance/options/{symbol}"
    root = _fetch(base)
    try:
        res = root["optionChain"]["result"][0]
    except (TypeError, KeyError, IndexError):
        return None
    spot = (res.get("quote") or {}).get("regularMarketPrice")
    exps = res.get("expirationDates") or []
    if not spot or not exps:
        return None
    now = dt.datetime.now(dt.timezone.utc)
    horizon = now + dt.timedelta(days=MAX_EXPIRY_DAYS)
    picked = [e for e in sorted(exps)
              if now.timestamp() <= e <= horizon.timestamp()][:MAX_EXPIRIES]
    contracts: list[dict] = []
    for i, epoch in enumerate(picked):
        data = res if i == 0 and picked[0] == sorted(exps)[0] else _fetch(f"{base}?date={epoch}")
        if not data:
            continue
        try:
            opt = data["optionChain"]["result"][0]["options"][0]
        except (TypeError, KeyError, IndexError):
            continue
        exp_dt = dt.datetime.fromtimestamp(epoch, dt.timezone.utc)
        T = max((exp_dt - now).total_seconds() / (365 * 86400), 1e-6)
        for kind, legs in (("call", opt.get("calls", [])), ("put", opt.get("puts", []))):
            for c in legs:
                oi = c.get("openInterest") or 0
                iv = c.get("impliedVolatility") or 0
                K = c.get("strike")
                if oi and iv and K:
                    contracts.append({"K": float(K), "oi": int(oi), "iv": float(iv),
                                      "T": T, "kind": kind})
        time.sleep(0.25)
    return (float(spot), contracts) if contracts else None


def _gex_at(S: float, contracts: list[dict]) -> float:
    """Celkové dealer GEX ($ na 1% pohyb) při hypotetickém spotu S."""
    total = 0.0
    for c in contracts:
        g = _bs_gamma(S, c["K"], c["T"], c["iv"])
        sign = 1.0 if c["kind"] == "call" else -1.0
        total += sign * g * c["oi"] * CONTRACT_MULT * S * S * 0.01
    return total


def _flip_level(spot: float, contracts: list[dict], net: float) -> float | None:
    """Gamma flip = spot, kde net GEX = 0. Sken hypotetického spotu ±20 %, interpolace."""
    lo, hi = spot * 0.80, spot * 1.20
    steps = 60
    prev_S = lo
    prev_v = _gex_at(lo, contracts)
    for i in range(1, steps + 1):
        S = lo + (hi - lo) * i / steps
        v = _gex_at(S, contracts)
        if prev_v == 0:
            return round(prev_S, 2)
        if (prev_v < 0) != (v < 0):  # změna znaménka → lineární interpolace
            t = prev_v / (prev_v - v)
            return round(prev_S + t * (S - prev_S), 2)
        prev_S, prev_v = S, v
    return None


def _analyze(symbol: str, spot: float, contracts: list[dict]) -> dict:
    call_by_strike: dict[float, float] = {}
    put_by_strike: dict[float, float] = {}
    net_by_strike: dict[float, float] = {}
    for c in contracts:
        g = _bs_gamma(spot, c["K"], c["T"], c["iv"])
        gex = g * c["oi"] * CONTRACT_MULT * spot * spot * 0.01
        if c["kind"] == "call":
            call_by_strike[c["K"]] = call_by_strike.get(c["K"], 0) + gex
            net_by_strike[c["K"]] = net_by_strike.get(c["K"], 0) + gex
        else:
            put_by_strike[c["K"]] = put_by_strike.get(c["K"], 0) + gex
            net_by_strike[c["K"]] = net_by_strike.get(c["K"], 0) - gex
    net = _gex_at(spot, contracts)
    call_wall = max(call_by_strike, key=call_by_strike.get) if call_by_strike else None
    put_wall = max(put_by_strike, key=put_by_strike.get) if put_by_strike else None  # max put gamma = support
    # Profil kolem spotu (±12 %), seřazený, pro mini-graf
    lo, hi = spot * 0.88, spot * 1.12
    profile = sorted(({"strike": k, "gex": round(v, 0)}
                      for k, v in net_by_strike.items() if lo <= k <= hi),
                     key=lambda x: x["strike"])
    return {
        "underlying": symbol,
        "spot": round(spot, 2),
        "net_gex": round(net, 0),
        "regime": "positive" if net >= 0 else "negative",
        "flip": _flip_level(spot, contracts, net),
        "call_wall": call_wall,
        "put_wall": put_wall,
        "profile": profile,
        "contracts": len(contracts),
    }


def _push(base: str, payload: dict) -> None:
    token = os.environ.get("TRADEZER_TOKEN", "").strip()
    if not token:
        print("  --push přeskočen: chybí TRADEZER_TOKEN")
        return
    url = base.rstrip("/") + "/api/gamma/ingest"
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
    ap = argparse.ArgumentParser(description="Gamma exposure (GEX) screener")
    ap.add_argument("--push", action="store_true", help="pushni na /api/gamma/ingest")
    ap.add_argument("--base", default=os.environ.get("TRADEZER_BASE_URL", "https://tradezer.app"))
    ap.add_argument("--no-file", action="store_true", help="nezapisuj lokální gamma.json")
    args = ap.parse_args()

    instruments: dict[str, dict] = {}
    for inst, sym in UNDERLYINGS.items():
        print(f"GEX {inst} ({sym})…")
        chain = _load_chain(sym)
        if not chain:
            print(f"  {sym}: chain nedostupný, přeskočeno")
            continue
        instruments[inst] = _analyze(sym, *chain)
        r = instruments[inst]
        print(f"  spot {r['spot']} · net GEX {r['net_gex']:,.0f} ({r['regime']}) · "
              f"flip {r['flip']} · call wall {r['call_wall']} · put wall {r['put_wall']}")

    out = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "note": "Dealer gamma exposure z options OI (model dle standardní konvence, ne "
                "přesná pravda). Pozitivní = tlumené/mean-revert, negativní = trendové/volatilní.",
        "instruments": instruments,
    }
    if not args.no_file:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"-> {OUT} ({len(instruments)} instrumentů)")
    if args.push:
        _push(args.base, out)


if __name__ == "__main__":
    main()
