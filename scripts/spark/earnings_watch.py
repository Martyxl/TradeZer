#!/usr/bin/env python3
"""Earnings watch (Spark): hlídá výsledky hospodaření firem z Valuation radaru a co nejdřív je
pošle do Tradezeru k AI vysvětlení.

Zdroj: SEC EDGAR — firma musí výsledky do pár minut po vydání tiskové zprávy podat jako 8-K
(Item 2.02, tisková zpráva = exhibit 99.1). Konsenzus EPS: Nasdaq earnings kalendář.
Reakce ceny: Yahoo chart (5m vč. pre/after-hours) — průběžně 30 h po zveřejnění.

Nezatěžuje Neon: stav (viděné filingy) drží lokálně v JSON, do DB jde jen přes API při novém reportu.

Spuštění (systemd, appvenv kvůli httpx):
  EnvironmentFile=~/tradezer/scans.env  (TRADEZER_TOKEN, volitelně TRADEZER_BASE_URL)
  ~/tradezer/appvenv/bin/python ~/tradezer/earnings_watch.py --loop 120
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

BASE = os.environ.get("TRADEZER_BASE_URL", "https://tradezer.app")
TOKEN = os.environ.get("TRADEZER_TOKEN", "")
STATE = Path(os.environ.get("EARNINGS_STATE", str(Path.home() / "tradezer" / "earnings_state.json")))
LOOKBACK_DAYS = int(os.environ.get("EARNINGS_LOOKBACK_DAYS", "7"))
SEC_UA = {"User-Agent": "Tradezer research contact@tradezer.app", "Accept-Encoding": "gzip, deflate"}
WEB_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
          "Accept": "application/json,text/plain,*/*"}
NY = ZoneInfo("America/New_York")
REACTION_EVERY = 600        # s
REACTION_WINDOW_H = 30


def log(*a):
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except Exception:  # noqa: BLE001
        return {"seen": {}, "watch": {}}


def save_state(st: dict) -> None:
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=1))
    tmp.replace(STATE)


def api(method: str, path: str, **kw):
    r = httpx.request(method, f"{BASE}{path}", headers={"X-Internal-Token": TOKEN}, timeout=90, **kw)
    r.raise_for_status()
    return r.json()


# ------------------------------------------------------------------ SEC

def cik_map(st: dict) -> dict[str, int]:
    if st.get("cik") and time.time() - st.get("cik_at", 0) < 86400:
        return st["cik"]
    data = httpx.get("https://www.sec.gov/files/company_tickers.json", headers=SEC_UA, timeout=30).json()
    st["cik"] = {v["ticker"].upper(): int(v["cik_str"]) for v in data.values()}
    st["cik_at"] = time.time()
    return st["cik"]


def universe(st: dict) -> list[str]:
    if st.get("universe") and time.time() - st.get("universe_at", 0) < 6 * 3600:
        return st["universe"]
    st["universe"] = api("GET", "/api/valuation/universe")["tickers"]
    st["universe_at"] = time.time()
    return st["universe"]


def earnings_filings(cik: int, since: datetime) -> list[dict]:
    """8-K s Item 2.02 (výsledky hospodaření) podané po `since`."""
    r = httpx.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", headers=SEC_UA, timeout=20)
    r.raise_for_status()
    f = r.json()["filings"]["recent"]
    out = []
    for i in range(min(40, len(f["form"]))):
        if f["form"][i] != "8-K" or "2.02" not in (f["items"][i] or ""):
            continue
        acc_at = datetime.fromisoformat(f["acceptanceDateTime"][i].replace("Z", "+00:00"))
        if acc_at < since:
            continue
        out.append({"accession": f["accessionNumber"][i], "accepted_at": acc_at,
                    "primary": f["primaryDocument"][i]})
    return out


def _html_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</h\d>", "\n", raw)
    raw = re.sub(r"(?i)</td>", " | ", raw)
    txt = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    txt = re.sub(r"[ \t ]+", " ", txt)
    return re.sub(r"\n\s*\n+", "\n", txt).strip()


def press_release(cik: int, accession: str, primary: str) -> tuple[str, str]:
    """(text tiskové zprávy EX-99.1, URL). Fallback = hlavní dokument 8-K."""
    folder = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}"
    doc = None
    # Typ dokumentu podle SEC hlavičky (názvy souborů si firmy volí libovolně, např. „q326lillysales…htm“)
    try:
        hdr = httpx.get(f"{folder}/{accession}-index-headers.html", headers=SEC_UA, timeout=20).text
        docs = re.findall(r"<TYPE>\s*(EX-99[^\s<]*)[\s\S]*?<FILENAME>\s*([^\s<]+)", html.unescape(hdr), re.I)
        docs.sort(key=lambda d: d[0].upper() not in ("EX-99.1", "EX-99.01"))
        doc = docs[0][1] if docs else None
    except Exception:  # noqa: BLE001
        pass
    if not doc:
        # Záloha: největší HTML dokument mimo hlavní 8-K a XBRL náhledy (R1.htm…)
        items = httpx.get(f"{folder}/index.json", headers=SEC_UA, timeout=20).json()["directory"]["item"]
        cands = [(int(it.get("size") or 0), it["name"]) for it in items
                 if it["name"].lower().endswith((".htm", ".html")) and it["name"] != primary
                 and not re.match(r"(R\d+|.*index.*)\.html?$", it["name"], re.I)]
        doc = max(cands)[1] if cands else primary
    time.sleep(0.2)
    raw = httpx.get(f"{folder}/{doc}", headers=SEC_UA, timeout=30).text
    return _html_text(raw)[:60_000], f"{folder}/{doc}"


# ------------------------------------------------------------------ konsenzus + cena

def _money(v) -> float | None:
    if not v or v in ("N/A", "--"):
        return None
    s = str(v).replace("$", "").replace(",", "").strip()
    neg = s.startswith("(") and s.endswith(")")
    try:
        x = float(s.strip("()"))
    except ValueError:
        return None
    return -x if neg else x


def nasdaq_eps(ticker: str, accepted: datetime) -> dict:
    """Konsenzus EPS (+ skutečné EPS a překvapení, pokud už je Nasdaq má)."""
    d0 = accepted.astimezone(NY).date()
    for d in (d0, d0 + timedelta(days=1), d0 - timedelta(days=1)):
        try:
            rows = (httpx.get("https://api.nasdaq.com/api/calendar/earnings", params={"date": d.isoformat()},
                              headers=WEB_UA, timeout=20).json().get("data") or {}).get("rows") or []
        except Exception:  # noqa: BLE001
            continue
        row = next((r for r in rows if (r.get("symbol") or "").upper() == ticker.upper()), None)
        if row:
            n = str(row.get("noOfEsts") or "").strip()
            sur = row.get("surprise")
            return {"eps_estimate": _money(row.get("epsForecast")), "eps_actual": _money(row.get("eps")),
                    "eps_surprise_pct": _money(sur) if sur not in (None, "N/A", "") else None,
                    "n_estimates": n if n.isdigit() else None}
    return {}


def nasdaq_prices(ticker: str, accepted: datetime) -> tuple[float | None, float | None]:
    """(close před zveřejněním, aktuální cena vč. pre/after-hours) z Nasdaq API."""
    et = accepted.astimezone(NY)
    # Po 16:00 ET → reakce se měří od close téhož dne; jinak od close předchozího obchodního dne.
    cutoff = et.date() if et.hour >= 16 else et.date() - timedelta(days=1)
    hist = (httpx.get(f"https://api.nasdaq.com/api/quote/{ticker}/historical", headers=WEB_UA, timeout=20, params={
        "assetclass": "stocks", "fromdate": (cutoff - timedelta(days=10)).isoformat(), "todate": cutoff.isoformat(),
        "limit": 20}).json().get("data") or {}).get("tradesTable", {}).get("rows") or []
    closes = sorted(((datetime.strptime(r["date"], "%m/%d/%Y").date(), _money(r.get("close"))) for r in hist),
                    key=lambda x: x[0])
    before = next((c for d, c in reversed(closes) if d <= cutoff and c), None)
    info = (httpx.get(f"https://api.nasdaq.com/api/quote/{ticker}/info", params={"assetclass": "stocks"},
                      headers=WEB_UA, timeout=20).json().get("data") or {})
    cur = _money((info.get("primaryData") or {}).get("lastSalePrice"))
    return before, cur


def prices(ticker: str, accepted: datetime) -> tuple[float | None, float | None]:
    try:
        before, cur = nasdaq_prices(ticker, accepted)
        if before and cur:
            return before, cur
    except Exception as e:  # noqa: BLE001
        log("nasdaq price fail", ticker, str(e)[:120])
    r = httpx.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
                  params={"range": "5d", "interval": "5m", "includePrePost": "true"}, headers=WEB_UA, timeout=20)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    closes = res["indicators"]["quote"][0]["close"]
    bars = [(t, c) for t, c in zip(res.get("timestamp") or [], closes) if c is not None]
    ts = accepted.timestamp()
    before = [c for t, c in bars if t + 300 <= ts]
    return (before[-1] if before else None), (bars[-1][1] if bars else None)


# ------------------------------------------------------------------ hlavní smyčka

def scan(st: dict) -> None:
    ciks, tickers = cik_map(st), universe(st)
    since = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    for t in tickers:
        cik = ciks.get(t.upper()) or ciks.get(t.upper().replace(".", "-"))
        if not cik:
            continue
        try:
            filings = earnings_filings(cik, since)
        except Exception as e:  # noqa: BLE001
            log("SEC submissions fail", t, str(e)[:120])
            continue
        finally:
            time.sleep(0.15)
        for f in filings:
            if f["accession"] in st["seen"]:
                continue
            try:
                text, url = press_release(cik, f["accession"], f["primary"])
                eps = nasdaq_eps(t, f["accepted_at"])
                res = api("POST", "/api/valuation/earnings/ingest", json={
                    "ticker": t, "accession": f["accession"], "accepted_at": f["accepted_at"].isoformat(),
                    "url": url, "press_text": text, **eps})
                st["seen"][f["accession"]] = res["id"]
                st["watch"][str(res["id"])] = {"ticker": t, "accepted_at": f["accepted_at"].isoformat(), "last": 0}
                save_state(st)
                log("EARNINGS", t, f["accession"], res)
            except Exception as e:  # noqa: BLE001
                log("ingest fail", t, f["accession"], str(e)[:200])


def reactions(st: dict) -> None:
    now = time.time()
    for rid, w in list(st["watch"].items()):
        acc = datetime.fromisoformat(w["accepted_at"])
        expired = datetime.now(timezone.utc) - acc > timedelta(hours=REACTION_WINDOW_H)
        if expired and w.get("last"):
            del st["watch"][rid]
            continue
        # Starší report (doplněný zpětně) dostane reakci jednou — pohyb od zveřejnění do teď.
        if now - w.get("last", 0) < REACTION_EVERY:
            continue
        try:
            before, cur = prices(w["ticker"], acc)
            if before and cur:
                res = api("POST", f"/api/valuation/earnings/{rid}/reaction",
                          json={"price_before": before, "price_now": cur})
                log("reaction", w["ticker"], res)
            w["last"] = now
        except Exception as e:  # noqa: BLE001
            log("reaction fail", w["ticker"], str(e)[:160])
    save_state(st)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=int, default=0, help="interval v s (0 = jeden běh)")
    a = ap.parse_args()
    if not TOKEN:
        sys.exit("Chybí TRADEZER_TOKEN")
    while True:
        st = load_state()
        try:
            scan(st)
            reactions(st)
        except Exception as e:  # noqa: BLE001
            log("cycle fail", str(e)[:200])
        save_state(st)
        if not a.loop:
            break
        time.sleep(a.loop)


if __name__ == "__main__":
    main()
