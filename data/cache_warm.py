"""Udržuje CDN cache a funkci v TEPLE — uživatel nikdy nečeká na studenou funkci (8–16 s).

Běží na Sparku (v Česku = stejný edge region jako uživatelé; GitHub Actions z USA by zahřálo
jiný region). Každých 15 min (služba `--loop 900`; snížené kvůli Hobby limitu Active CPU) stáhne agregované dashboardy + veřejný fond. Díky
`s-maxage=300, stale-while-revalidate=3600` zůstanou položky v cache čerstvé a návštěvník dostane
odpověď z edge (~50–150 ms); funkce se probudí jen na pozadí (1 volání/URL/tick).

Použití:  python3 cache_warm.py --loop 300        (jednorázově bez --loop)
Env:      TRADEZER_BASE_URL (default https://tradezer.app), WARM_TICKERS (default XAUUSD,ES,NQ,YM,EURUSD,GBPUSD,USDJPY)
"""
import argparse
import os
import time
import urllib.error
import urllib.request

BASE = os.environ.get("TRADEZER_BASE_URL", "https://tradezer.app").rstrip("/")
TICKERS = [t.strip().upper() for t in os.environ.get("WARM_TICKERS", "XAUUSD,ES,NQ,YM,EURUSD,GBPUSD,USDJPY").split(",") if t.strip()]
UA = "Mozilla/5.0 TradezerCacheWarm/1.0"


def urls() -> list[str]:
    return [f"/api/dashboard?ticker={t}" for t in TICKERS] + ["/api/fund"]


def warm_once() -> list[tuple[str, int, float, str]]:
    out = []
    for path in urls():
        t0 = time.time()
        try:
            req = urllib.request.Request(BASE + path, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                r.read()
                out.append((path, r.status, time.time() - t0, r.headers.get("x-vercel-cache", "-")))
        except urllib.error.HTTPError as e:
            out.append((path, e.code, time.time() - t0, "-"))
        except (urllib.error.URLError, TimeoutError, OSError):
            out.append((path, 0, time.time() - t0, "-"))
        time.sleep(0.5)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=int, default=0, help="opakuj každých N sekund")
    args = ap.parse_args()
    while True:
        res = warm_once()
        print(f"[{time.strftime('%H:%M:%S')}] " + " | ".join(
            f"{p.split('=')[-1] if 'dashboard' in p else p} {s} {ms*1000:.0f}ms {c}" for p, s, ms, c in res), flush=True)
        if args.loop <= 0:
            return
        time.sleep(args.loop)


if __name__ == "__main__":
    main()
