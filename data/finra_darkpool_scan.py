"""Dark Pool scan — FINRA OTC/ATS Transparency (off-exchange „dark pool" objemy).

Veřejné FINRA API (bez auth): ATS_W_SMBL = týdenní ATS objem per symbol. Data mají
~měsíční zpoždění publikace. Najde nejnovější dostupný týden, stáhne ho (stránkovaně,
API cap 5000/stránku), seřadí dle notional a pushne top N na backend.

Env:
    TRADEZER_TOKEN    — X-Internal-Token
    TRADEZER_BASE_URL — cíl (default https://tradezer.app)
Spuštění:  TRADEZER_TOKEN=... py data/finra_darkpool_scan.py --push   (--loop N minut)
"""
import argparse
import datetime as dt
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

UA = "Mozilla/5.0 TradezerDarkPool/1.0"
FINRA = "https://api.finra.org/data/group/otcMarket/name/weeklySummary"
TOP_N = 60


def _finra(body: dict) -> list:
    req = urllib.request.Request(FINRA, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json",
                                          "Accept": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode().strip()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
        print(f"  FINRA fail: {e}")
        return []
    if not raw:  # prázdné tělo = žádná data (ne chyba)
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    return data if isinstance(data, list) else []


_TYPE = {"fieldName": "summaryTypeCode", "compareType": "EQUAL", "fieldValue": "ATS_W_SMBL"}


def latest_week() -> str | None:
    """Nejnovější dostupný týden — iterace pondělků zpět (orderBy API nespolehlivé)."""
    today = dt.date.today()
    monday = today - dt.timedelta(days=today.weekday())
    for i in range(26):  # ~půl roku zpět (data mají zpoždění)
        wk = (monday - dt.timedelta(days=7 * i)).isoformat()
        rows = _finra({"limit": 1, "compareFilters": [_TYPE,
                      {"fieldName": "weekStartDate", "compareType": "EQUAL", "fieldValue": wk}]})
        if rows:
            return wk
        time.sleep(0.4)
    return None


def fetch_week(week: str) -> list[dict]:
    flt = [_TYPE, {"fieldName": "weekStartDate", "compareType": "EQUAL", "fieldValue": week}]
    out, offset = [], 0
    while True:
        page = _finra({"limit": 5000, "offset": offset, "compareFilters": flt})
        out.extend(page)
        if len(page) < 5000:
            break
        offset += 5000
        time.sleep(0.4)
    return out


def build_items(rows: list[dict]) -> list[dict]:
    rows.sort(key=lambda r: r.get("totalNotionalSum") or 0, reverse=True)
    items = []
    for r in rows[:TOP_N]:
        shares = r.get("totalWeeklyShareQuantity") or 0
        trades = r.get("totalWeeklyTradeCount") or 0
        notional = r.get("totalNotionalSum") or 0
        items.append({
            "symbol": r.get("issueSymbolIdentifier"),
            "name": (r.get("issueName") or "")[:80],
            "shares": round(shares),
            "trades": trades,
            "notional": round(notional),
            "avg_trade": round(notional / trades) if trades else None,
            "tier": r.get("tierDescription"),
        })
    return items


def push(base: str, token: str, payload: dict) -> None:
    req = urllib.request.Request(f"{base}/api/darkpool/ingest", data=json.dumps(payload).encode(),
                                 method="POST", headers={"Content-Type": "application/json",
                                 "X-Internal-Token": token, "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"  push OK: {r.read().decode()[:120]}")
    except urllib.error.HTTPError as e:
        print(f"  push HTTP {e.code}: {e.read().decode()[:120]}")
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"  push fail {e}")


def run_once(base: str, token: str, do_push: bool) -> None:
    wk = latest_week()
    if not wk:
        print("  žádný dostupný týden")
        return
    rows = fetch_week(wk)
    items = build_items(rows)
    print(f"  týden {wk}: {len(rows)} symbolů, top {len(items)} dle notional")
    for it in items[:5]:
        print(f"    {it['symbol']} ${it['notional']/1e6:.0f}M ({it['trades']} trades)")
    payload = {"week": wk, "count": len(items), "universe_size": len(rows),
               "items": items, "source": "FINRA ATS (OTC Transparency)"}
    if do_push:
        if not token:
            print("  --push přeskočen: chybí TRADEZER_TOKEN")
        else:
            push(base, token, payload)
    else:
        print(json.dumps(payload, ensure_ascii=False)[:300])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("TRADEZER_BASE_URL", "https://tradezer.app"))
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--loop", type=int, default=0, help="opakuj každých N minut (Spark: 10080 = týdně)")
    args = ap.parse_args()
    token = os.environ.get("TRADEZER_TOKEN", "").strip()
    base = args.base.rstrip("/")
    while True:
        print(f"[{time.strftime('%Y-%m-%d %H:%M')}] dark pool scan -> {base}")
        run_once(base, token, args.push)
        if args.loop <= 0:
            break
        time.sleep(args.loop * 60)


if __name__ == "__main__":
    main()
