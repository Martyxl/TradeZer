#!/usr/bin/env python3
"""Analytici a vlastníci firem z radaru (Twelve Data) → detail firmy ve Valuation Radaru.

Pro každou firmu z radaru 1× denně: cílová cena analytiků, doporučení (a jak se měnila), revize
odhadů EPS (kolik analytiků zvýšilo/snížilo + jak se konsenzus pohnul za 7/30/90 dní), očekávaný
růst, poslední akce analytiků (upgrade/downgrade, změna cílové ceny) a největší institucionální
vlastníci a fondy. Výsledek pushne na /api/valuation/analysts/ingest. Jen stdlib.
Běh (Spark): TWELVEDATA_API_KEY=… TRADEZER_TOKEN=… python3 analyst_scan.py [--loop 1440]
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

BASE = os.environ.get("TRADEZER_BASE_URL", "https://tradezer.app").rstrip("/")
TOKEN = os.environ.get("TRADEZER_TOKEN", "")
TD_KEY = os.environ.get("TWELVEDATA_API_KEY", "")


def log(*a):
    print(datetime.now().strftime("%H:%M:%S"), *a, flush=True)


def _req(url, headers, data=None, method="GET"):
    req = urllib.request.Request(url, headers=headers, data=data, method=method)
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode())


def td(path, **params):
    try:
        d = _req(f"https://api.twelvedata.com/{path}?" + urllib.parse.urlencode(params),
                 {"Authorization": f"apikey {TD_KEY}"})
    except Exception as e:  # noqa: BLE001
        log("TD fail", path, params.get("symbol"), str(e)[:100])
        return {}
    return d if isinstance(d, dict) and d.get("status") != "error" else {}


def _f(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _chg(now, then):
    """% změna vůči |then| — kladná = odhad se zlepšil i u ztrátových firem (−1,45 → −0,96 = +34 %)."""
    return round((now - then) / abs(then) * 100, 2) if now is not None and then not in (None, 0) else None


def _growth(v, cap):
    """Růst v % — nesmyslné hodnoty (základna blízko nuly, −145 % p.a.) zahodit."""
    x = _f(v)
    return round(x * 100, 1) if x is not None and abs(x * 100) <= cap else None


def collect(t: str) -> dict:
    out: dict = {"ticker": t}
    pt = td("price_target", symbol=t).get("price_target") or {}
    if pt.get("average"):
        cur = _f(pt.get("current"))
        out["price_target"] = {k: _f(pt.get(k)) for k in ("low", "median", "average", "high", "current")}
        out["price_target"]["upside_pct"] = _chg(_f(pt.get("average")), cur)
    rec = td("recommendations", symbol=t)
    if rec.get("trends"):
        out["recommendations"] = {"now": rec["trends"].get("current_month"),
                                  "3m_ago": rec["trends"].get("3_months_ago"), "rating": _f(rec.get("rating"))}
    trend = {r.get("period"): r for r in td("eps_trend", symbol=t).get("eps_trend") or []}
    revs = {r.get("period"): r for r in td("eps_revisions", symbol=t).get("eps_revision") or []}
    rows = []
    for per in ("current_quarter", "current_year", "next_year"):
        tr, rv = trend.get(per) or {}, revs.get(per) or {}
        if not tr and not rv:
            continue
        now = _f(tr.get("current_estimate"))
        rows.append({"period": per, "date": tr.get("date") or rv.get("date"), "eps": now,
                     "chg_7d": _chg(now, _f(tr.get("7_days_ago"))), "chg_30d": _chg(now, _f(tr.get("30_days_ago"))),
                     "chg_90d": _chg(now, _f(tr.get("90_days_ago"))),
                     "up_month": rv.get("up_last_month"), "down_month": rv.get("down_last_month")})
    if rows:
        out["revisions"] = rows
    g = td("growth_estimates", symbol=t).get("growth_estimates") or {}
    if g:
        out["growth"] = {k: _growth(g.get(k), 300) for k in ("current_quarter", "next_quarter", "current_year", "next_year")}
        out["growth"]["next_5_years_pa"] = _growth(g.get("next_5_years_pa"), 100)
    ra = td("analyst_ratings/us_equities", symbol=t, outputsize=8).get("ratings") or []
    out["actions"] = [{k: r.get(k) for k in ("date", "firm", "rating_change", "rating_current", "rating_prior",
                                             "price_target_current", "price_target_prior")} for r in ra[:8]]
    inst = td("institutional_holders", symbol=t).get("institutional_holders") or []
    fund = td("fund_holders", symbol=t).get("fund_holders") or []
    out["holders"] = {
        "institutions": [{"name": h.get("entity_name"), "pct": _f(h.get("percent_held")), "value": _f(h.get("value")),
                          "date": h.get("date_reported")} for h in inst[:8]],
        "funds": [{"name": h.get("entity_name"), "pct": _f(h.get("percent_held")), "value": _f(h.get("value")),
                   "date": h.get("date_reported")} for h in fund[:6]],
    }
    return out


def run_once():
    hdr = {"X-Internal-Token": TOKEN, "Content-Type": "application/json"}
    tickers = _req(f"{BASE}/api/valuation/universe", hdr)["tickers"]
    items = []
    for t in tickers:
        items.append(collect(t))
        time.sleep(0.2)
    res = _req(f"{BASE}/api/valuation/analysts/ingest", hdr, json.dumps({"items": items}).encode(), "POST")
    log("analytici:", len(items), "firem →", res)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=int, default=0, help="interval v minutách (0 = jeden běh)")
    a = ap.parse_args()
    if not (TD_KEY and TOKEN):
        sys.exit("Chybí TWELVEDATA_API_KEY nebo TRADEZER_TOKEN")
    while True:
        if not a.loop or datetime.now().weekday() < 5:   # o víkendu nebudit DB (Neon autosuspend)
            try:
                run_once()
            except Exception as e:  # noqa: BLE001
                log("chyba", str(e)[:200])
        if not a.loop:
            break
        time.sleep(a.loop * 60)


if __name__ == "__main__":
    main()
