"""Smart Money — insider aktivita (SEC Form 4) z EDGAR full-text search, ZDARMA.

Stáhne nejnovější Form 4 filingy (EFTS), naparsuje open-market nákupy/prodeje
(transactionCode P/S) + roli insidera (director/officer/10% owner), hodnotu obchodu,
z toho postaví žebříček „chytrých peněz". Push-vzor jako Discovery/Gamma.

Congress obchody (Senate/House) sem přijdou později — free mirrory mezitím zmizely
(S3 403 / Quiver za klíčem), CapitolTrades jde jen z rezidenční IP. Insider je spolehlivý.

Spuštění:
    py data/smart_money_scan.py            # zapíše web/public/smart_money.json
    py data/smart_money_scan.py --push     # + pushne na /api/smart-money/ingest

Env (--push): TRADEZER_TOKEN, volitelně TRADEZER_BASE_URL. SEC EDGAR jde i z datacentra
(narozdíl od Yahoo) → tenhle sken by šel i z CI, ale držíme jednotný push-vzor.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "web" / "public" / "smart_money.json"
# SEC vyžaduje popisný User-Agent s kontaktem (jinak 403).
UA = "Tradezer/1.0 (tradezer.app; contact martyxl@gmail.com)"

LOOKBACK_DAYS = 3        # okno Form 4 filingů
MAX_PAGES = 3            # EFTS stránky po 100 (3 = až 300 filingů)
MAX_ROWS = 250           # strop řádků ve snapshotu
SEC_PACE = 0.13          # ~8 req/s (SEC limit je 10/s)
_last_req = 0.0


def _get(url: str) -> str | None:
    global _last_req
    wait = SEC_PACE - (time.time() - _last_req)
    if wait > 0:
        time.sleep(wait)
    _last_req = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip, deflate"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                import gzip
                raw = gzip.decompress(raw)
            return raw.decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        print(f"  fetch fail {e}")
        return None


def _truthy(v: str | None) -> bool:
    return (v or "").strip() in ("1", "true", "True")


def _role(rel: ET.Element | None) -> str:
    if rel is None:
        return "insider"
    if _truthy(rel.findtext("isDirector")):
        return "director"
    if _truthy(rel.findtext("isOfficer")):
        return (rel.findtext("officerTitle") or "officer").strip()[:40]
    if _truthy(rel.findtext("isTenPercentOwner")):
        return "10% owner"
    return "insider"


def _parse_form4(xml: str) -> list[dict]:
    """Vrátí seznam open-market transakcí (P/S) z jednoho Form 4."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    sym = (root.findtext("issuer/issuerTradingSymbol") or "").strip().upper()
    issuer = (root.findtext("issuer/issuerName") or "").strip()
    owner = (root.findtext("reportingOwner/reportingOwnerId/rptOwnerName") or "").strip()
    role = _role(root.find("reportingOwner/reportingOwnerRelationship"))
    if not sym:
        return []
    rows = []
    for tx in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        code = (tx.findtext("transactionCoding/transactionCode") or "").strip()
        if code not in ("P", "S"):   # jen open-market nákup/prodej
            continue
        try:
            shares = float(tx.findtext("transactionAmounts/transactionShares/value") or 0)
            price = float(tx.findtext("transactionAmounts/transactionPricePerShare/value") or 0)
        except ValueError:
            continue
        date = (tx.findtext("transactionDate/value") or "").strip()
        rows.append({
            "date": date, "person": owner, "role": role,
            "ticker": sym, "issuer": issuer[:60],
            "tx": "buy" if code == "P" else "sell",
            "shares": round(shares), "price": round(price, 2),
            "value": round(shares * price),
        })
    return rows


def _doc_url(accession: str, cik: str, fname: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{cik.lstrip('0')}/{accession.replace('-', '')}/{fname}"


def _scan() -> list[dict]:
    end = dt.date.today()
    start = end - dt.timedelta(days=LOOKBACK_DAYS)
    rows: list[dict] = []
    seen = 0
    for page in range(MAX_PAGES):
        url = (f"https://efts.sec.gov/LATEST/search-index?forms=4"
               f"&startdt={start}&enddt={end}&from={page * 100}")
        data = _get(url)
        if not data:
            break
        try:
            hits = json.loads(data)["hits"]["hits"]
        except (ValueError, KeyError):
            break
        if not hits:
            break
        for h in hits:
            acc, fname = h["_id"].split(":", 1)
            ciks = h["_source"].get("ciks") or []
            cik = acc.split("-", 1)[0]  # accession vede CIK filera = kanonická cesta
            xml = _get(_doc_url(acc, cik, fname))
            if not xml and ciks:  # fallback přes uvedené CIKy
                for c in ciks:
                    xml = _get(_doc_url(acc, c, fname))
                    if xml:
                        break
            if xml:
                rows.extend(_parse_form4(xml))
            seen += 1
        print(f"  strana {page + 1}: {seen} filingů, {len(rows)} transakcí")
    # nejnovější první, pak podle hodnoty
    rows.sort(key=lambda r: (r["date"], r["value"]), reverse=True)
    return rows[:MAX_ROWS]


def _aggregate(rows: list[dict]) -> dict:
    by_ticker: dict[str, dict] = {}
    for r in rows:
        t = by_ticker.setdefault(r["ticker"], {"ticker": r["ticker"], "issuer": r["issuer"],
                                               "buys": 0, "sells": 0, "buy_value": 0, "sell_value": 0})
        if r["tx"] == "buy":
            t["buys"] += 1
            t["buy_value"] += r["value"]
        else:
            t["sells"] += 1
            t["sell_value"] += r["value"]
    top_buys = sorted((t for t in by_ticker.values() if t["buys"]),
                      key=lambda x: x["buy_value"], reverse=True)[:10]
    return {"top_buys": top_buys}


def _push(base: str, payload: dict) -> None:
    token = os.environ.get("TRADEZER_TOKEN", "").strip()
    if not token:
        print("  --push přeskočen: chybí TRADEZER_TOKEN")
        return
    url = base.rstrip("/") + "/api/smart-money/ingest"
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
    ap = argparse.ArgumentParser(description="Smart Money — insider (SEC Form 4) screener")
    ap.add_argument("--push", action="store_true", help="pushni na /api/smart-money/ingest")
    ap.add_argument("--base", default=os.environ.get("TRADEZER_BASE_URL", "https://tradezer.app"))
    ap.add_argument("--no-file", action="store_true", help="nezapisuj lokální smart_money.json")
    args = ap.parse_args()

    print(f"Smart Money: SEC Form 4 za posledních {LOOKBACK_DAYS} dní…")
    rows = _scan()
    buys = sum(1 for r in rows if r["tx"] == "buy")
    out = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": "sec_form4",
        "note": "Insider obchody z SEC Form 4 (open-market nákup P / prodej S). Zdarma, "
                "veřejné regulatorní hlášení. Rozcestník, ne investiční doporučení.",
        "count": len(rows), "buys": buys, "sells": len(rows) - buys,
        **_aggregate(rows),
        "insiders": rows,
        "congress": [],  # placeholder — přijde free zdroj (viz hlavička)
    }
    print(f"  {len(rows)} transakcí ({buys} nákupů / {len(rows) - buys} prodejů)")
    if not args.no_file:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"-> {OUT}")
    if args.push:
        _push(args.base, out)


if __name__ == "__main__":
    main()
