"""Smart Money / Fondy — co drží, kupují a prodávají vybrané fondy (SEC 13F) + nové podíly nad 5 % (13D/13G).

13F-HR: čtvrtletní výpis dlouhých pozic v amerických akciích (do 45 dnů po konci čtvrtletí).
Porovnáním posledních dvou výpisů každého fondu vznikne: nová pozice / navýšení / snížení / prodáno celé.
Konsenzus = kolik fondů z výběru tutéž akcii kupuje / prodává (počítá se jen pozice ≥ 0,5 % portfolia
fondu, aby drobné úpravy velkých multi-strategy fondů nepřebily přesvědčené sázky).
13D/13G: podíl nad 5 % ve firmě, hlášení do 10 dnů (13D = aktivní/aktivistický záměr) — nejčerstvější signál.

Omezení (zobrazuje se i v UI): 13F nemá shorty ani zahraniční akcie, jde jen o stav ke konci čtvrtletí.

Zdroje zdarma: SEC EDGAR (submissions API, archiv filingů), OpenFIGI (CUSIP → ticker, bez klíče).
Cache (parsované výpisy, mapování CUSIP, 13D/G hlavičky) v FUNDS_CACHE → denní běh stáhne jen nové.

    py data/fund_holdings_scan.py            # zapíše web/public/smart_money_funds.json
    py data/fund_holdings_scan.py --push     # + pushne na /api/smart-money/funds/ingest

Env: TRADEZER_TOKEN (push), TRADEZER_BASE_URL, SEC_USER_AGENT (SEC chce popisný UA), FUNDS_CACHE.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "web" / "public" / "smart_money_funds.json"
CACHE = Path(os.environ.get("FUNDS_CACHE", Path(__file__).resolve().parent / "funds_cache.json"))
UA = os.environ.get("SEC_USER_AGENT", "Tradezer/1.0 (tradezer.app)")
SEC_PACE = 0.13          # ~8 req/s (limit SEC je 10/s)
FIGI_PACE = 2.6          # OpenFIGI bez klíče: 25 požadavků/min, 10 CUSIPů v jednom
SIGNIFICANT = 0.5        # % portfolia fondu, od kdy se změna počítá do konsenzu
CHANGE_MIN = 0.10        # ±10 % kusů = navýšení/snížení (menší je šum)
STAKE_DAYS = 120         # 13D/13G za posledních N dní
STALE_DAYS = 200         # výpis starší než tohle → fond se nepočítá do konsenzu

# (klíč, název, správce, styl, CIK). Výběr: koncentrované portfolio a známé jméno; čistě kvantové
# fondy a indexové giganty (Vanguard, BlackRock) chybí schválně — drží všechno, signál nenesou.
FUNDS = [
    ("berkshire", "Berkshire Hathaway", "Warren Buffett / Greg Abel", "value", 1067983),
    ("pershing", "Pershing Square", "Bill Ackman", "aktivista", 1336528),
    ("appaloosa", "Appaloosa", "David Tepper", "hedge", 1656456),
    ("duquesne", "Duquesne Family Office", "Stanley Druckenmiller", "makro", 1536411),
    ("thirdpoint", "Third Point", "Dan Loeb", "aktivista", 1040273),
    ("icahn", "Icahn", "Carl Icahn", "aktivista", 921669),
    ("elliott", "Elliott", "Paul Singer", "aktivista", 1791786),
    ("trian", "Trian", "Nelson Peltz", "aktivista", 1345471),
    ("valueact", "ValueAct", "Mason Morfit", "aktivista", 1418814),
    ("starboard", "Starboard Value", "Jeff Smith", "aktivista", 1517137),
    ("sachem", "Sachem Head", "Scott Ferguson", "aktivista", 1582090),
    ("baupost", "Baupost", "Seth Klarman", "value", 1061768),
    ("himalaya", "Himalaya Capital", "Li Lu", "value", 1709323),
    ("pabrai", "Dalal Street", "Mohnish Pabrai", "value", 1549575),
    ("akre", "Akre Capital", "Akre / Neff / Saler", "kvalita", 1112520),
    ("fundsmith", "Fundsmith", "Terry Smith", "kvalita", 1569205),
    ("ruane", "Ruane Cunniff (Sequoia)", "Ruane Cunniff", "kvalita", 1720792),
    ("polen", "Polen Capital", "Polen", "kvalita", 1034524),
    ("tci", "TCI", "Chris Hohn", "kvalita", 1647251),
    ("harris", "Harris Associates (Oakmark)", "Bill Nygren", "value", 813917),
    ("tweedy", "Tweedy, Browne", "Tweedy, Browne", "value", 732905),
    ("firsteagle", "First Eagle", "First Eagle", "value", 1325447),
    ("oaktree", "Oaktree", "Howard Marks", "value", 949509),
    ("gates", "Gates Foundation Trust", "Gates Foundation", "value", 1166559),
    ("tiger", "Tiger Global", "Chase Coleman", "růst/tech", 1167483),
    ("coatue", "Coatue", "Philippe Laffont", "růst/tech", 1135730),
    ("lonepine", "Lone Pine", "Stephen Mandel", "růst/tech", 1061165),
    ("viking", "Viking Global", "Andreas Halvorsen", "hedge", 1103804),
    ("d1", "D1 Capital", "Daniel Sundheim", "hedge", 1747057),
    ("altimeter", "Altimeter", "Brad Gerstner", "růst/tech", 1541617),
    ("whalerock", "Whale Rock", "Alex Sacerdote", "růst/tech", 1387322),
    ("durable", "Durable Capital", "Henry Ellenbogen", "růst/tech", 1798849),
    ("egerton", "Egerton Capital", "John Armitage", "hedge", 1581811),
    ("glenview", "Glenview", "Larry Robbins", "hedge", 1138995),
    ("maverick", "Maverick", "Lee Ainslie", "hedge", 934639),
    ("ark", "ARK Invest", "Cathie Wood", "růst/tech", 1697748),
    ("soros", "Soros Fund Management", "Soros", "makro", 1029160),
    ("bridgewater", "Bridgewater", "Bridgewater", "makro", 1350694),
    ("point72", "Point72", "Steve Cohen", "hedge", 1603466),
]

_last = 0.0


def _get(url: str, data: bytes | None = None, headers: dict | None = None, pace: float = SEC_PACE) -> str | None:
    global _last
    wait = pace - (time.time() - _last)
    if wait > 0:
        time.sleep(wait)
    _last = time.time()
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Accept-Encoding": "gzip", **(headers or {})})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    import gzip
                    raw = gzip.decompress(raw)
                return raw.decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                time.sleep(30 * (attempt + 1))
                continue
            if e.code != 404:
                print(f"  HTTP {e.code} {url[:110]}")
            return None
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            print(f"  fetch fail {e} {url[:110]}")
            return None
    return None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_infotable(xml: str) -> dict[str, dict]:
    """13F information table → {cusip: {name, value, shares}} — jen akcie (SH), bez opcí (put/call);
    řádky stejného CUSIPu (různí „other managers“) se sečtou."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return {}
    out: dict[str, dict] = {}
    for it in root.iter():
        if _local(it.tag) != "infoTable":
            continue
        f = {}
        for ch in it.iter():
            name = _local(ch.tag)
            if name in ("nameOfIssuer", "cusip", "value", "sshPrnamt", "sshPrnamtType", "putCall", "titleOfClass"):
                f[name] = (ch.text or "").strip()
        if f.get("putCall") or (f.get("sshPrnamtType") or "SH").upper() != "SH":
            continue
        cusip = (f.get("cusip") or "").upper()
        try:
            value, shares = float(f.get("value") or 0), float(f.get("sshPrnamt") or 0)
        except ValueError:
            continue
        if not cusip or shares <= 0:
            continue
        h = out.setdefault(cusip, {"name": f.get("nameOfIssuer", "")[:60], "value": 0.0, "shares": 0.0})
        h["value"] += value
        h["shares"] += shares
    return out


def _is_split(ratio: float, value_ratio: float) -> bool:
    """Počet kusů ×N (nebo ÷N) při zhruba stejné hodnotě = split, ne nákup/prodej."""
    for n in (2, 3, 4, 5, 8, 10, 15, 20, 25, 50):
        for r in (n, 1 / n):
            if abs(ratio / r - 1) < 0.02 and 0.5 < value_ratio < 2:
                return True
    return False


def compare(cur: dict[str, dict], prev: dict[str, dict] | None) -> list[dict]:
    """Pozice fondu s váhou a změnou proti minulému čtvrtletí (action: new/added/reduced/sold/hold)."""
    tot = sum(h["value"] for h in cur.values()) or 1
    ptot = sum(h["value"] for h in (prev or {}).values()) or 1
    rows = []
    for c, h in cur.items():
        p = (prev or {}).get(c)
        w = 100 * h["value"] / tot
        row = {"cusip": c, "name": h["name"], "value": round(h["value"]), "shares": h["shares"],
               "weight": round(w, 2), "prev_weight": round(100 * p["value"] / ptot, 2) if p else 0.0}
        if prev is None:
            row["action"] = "hold"
        elif not p:
            row["action"], row["chg_pct"] = "new", None
        else:
            ratio = h["shares"] / p["shares"]
            if _is_split(ratio, h["value"] / p["value"] if p["value"] else 1):
                ratio = 1.0
            row["chg_pct"] = round(100 * (ratio - 1), 1)
            row["action"] = "added" if ratio >= 1 + CHANGE_MIN else "reduced" if ratio <= 1 - CHANGE_MIN else "hold"
            if row["action"] != "hold":
                # dokoupené/prodané kusy × cena ke konci čtvrtletí
                row["flow"] = round((h["shares"] - p["shares"]) * h["value"] / h["shares"])
        if row["action"] == "new":
            row["flow"] = round(h["value"])
        rows.append(row)
    for c, p in (prev or {}).items():
        if c not in cur:
            rows.append({"cusip": c, "name": p["name"], "value": 0, "shares": 0, "weight": 0.0,
                         "prev_weight": round(100 * p["value"] / ptot, 2), "action": "sold", "chg_pct": -100.0,
                         "flow": -round(p["value"])})
    return rows


# ── EDGAR ────────────────────────────────────────────────────────────────────

def _submissions(cik: int) -> dict | None:
    raw = _get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    try:
        return json.loads(raw)["filings"]["recent"] if raw else None
    except (ValueError, KeyError):
        return None


def _filing_base(cik: int, acc: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/"


def _load_13f(cik: int, acc: str) -> dict | None:
    idx = _get(_filing_base(cik, acc) + "index.json")
    try:
        items = json.loads(idx)["directory"]["item"] if idx else []
    except (ValueError, KeyError):
        return None
    xmls = [x["name"] for x in items if x["name"].lower().endswith(".xml") and x["name"].lower() != "primary_doc.xml"]
    for name in xmls:
        xml = _get(_filing_base(cik, acc) + name)
        if xml and "infoTable" in xml:
            return parse_infotable(xml)
    return None


def _hdr_subject(hdr: str) -> tuple[str | None, str | None]:
    m = re.search(r"<SUBJECT-COMPANY>.*?<CONFORMED-NAME>([^\n<]+).*?<CIK>(\d+)", hdr or "", re.S)
    return (m.group(1).strip(), m.group(2).lstrip("0")) if m else (None, None)


def parse_percent(doc: str) -> float | None:
    """Nejvyšší „percent of class“ z XML Schedule 13D/13G (od 12/2024); staré textové verze → None."""
    vals = [float(v) for v in re.findall(r"<(?:\w+:)?(?:percentOfClass|classPercent)>\s*([\d.]+)", doc or "")]
    return max(vals) if vals else None


def _stake(cik: int, acc: str, form: str, primary: str) -> dict | None:
    base = _filing_base(cik, acc)
    name, subj = _hdr_subject(_get(base + acc + ".hdr.sgml") or "")
    if not subj or subj == str(cik):
        return {"skip": True}          # fond je tu předmětem (např. Berkshire), ne podavatelem
    pct = None
    if primary.lower().endswith(".xml"):
        pct = parse_percent(_get(base + primary.rsplit("/", 1)[-1]) or "")
    return {"issuer": name, "issuer_cik": subj, "percent": pct, "form": form,
            "url": base + (primary.rsplit("/", 1)[-1] if primary else "")}


# Burzovní kódy Bloombergu pro americké trhy (composite US + jednotlivé burzy).
_US_EXCH = {"US", "UN", "UW", "UQ", "UA", "UR", "UP", "UV", "UF", "UZ", "UD", "UC", "UB", "UT", "UX", "UM"}


def _figi(cusips: list[str], cache: dict, any_exchange: bool = False) -> None:
    """CUSIP → ticker. Druhý průchod (any_exchange) bez filtru burzy pro to, co první nenašel;
    bere se jen akcie z americké burzy (ne dluhopis)."""
    todo = [c for c in cusips if c not in cache]
    for i in range(0, len(todo), 10):
        chunk = todo[i:i + 10]
        jobs = [{"idType": "ID_CUSIP", "idValue": c, **({} if any_exchange else {"exchCode": "US"})} for c in chunk]
        body = json.dumps(jobs).encode()
        raw = _get("https://api.openfigi.com/v3/mapping", body, {"Content-Type": "application/json"}, pace=FIGI_PACE)
        try:
            res = json.loads(raw) if raw else None
        except ValueError:
            res = None
        if not isinstance(res, list):
            print("  OpenFIGI neodpověděl, zbytek CUSIPů příště")
            return
        for c, r in zip(chunk, res):
            if r.get("error"):
                continue                      # dočasná chyba → zkusit při dalším běhu
            data = r.get("data") or []
            if any_exchange:
                data = [d for d in data if d.get("exchCode") in _US_EXCH and d.get("marketSector") == "Equity"
                        and "bond" not in str(d.get("securityType2") or "").lower()]
            pick = next((d for d in data if d.get("marketSector") == "Equity"), data[0] if data else None)
            cache[c] = ((pick.get("ticker") or "").replace("/", "-") or None) if pick else None
        if (i // 10) % 20 == 19:
            print(f"  OpenFIGI {i + 10}/{len(todo)}")


def _company_tickers() -> tuple[dict[str, str], dict[str, str]]:
    """SEC seznam {CIK: ticker} a {normalizovaný název: ticker}. U firmy s víc tickery (prioritní
    akcie „BAC-PL“…) vyhraje kmenová akcie — první v pořadí a bez pomlčky."""
    raw = _get("https://www.sec.gov/files/company_tickers.json")
    try:
        rows = list(json.loads(raw).values()) if raw else []
    except ValueError:
        rows = []
    by_cik: dict[str, str] = {}
    by_name: dict[str, str] = {}
    for v in sorted(rows, key=lambda v: not re.fullmatch(r"[A-Z]{1,5}", str(v.get("ticker", "")))):
        t, cik, title = str(v.get("ticker") or ""), str(v.get("cik_str") or ""), norm_name(str(v.get("title") or ""))
        if t and cik:
            by_cik.setdefault(cik, t)
        if t and title:
            by_name.setdefault(title, t)
    return by_cik, by_name


_SUFFIX = {"INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "PLC", "PL", "NV", "N", "V", "SA", "S",
           "A", "AG", "SE", "SPA", "HLDG", "HLDGS", "HLDNGS", "HOLDING", "HOLDINGS", "GROUP", "GRP", "THE", "NEW",
           "DEL", "COM", "CL", "LP", "LLC", "TR", "IRELAND", "INTL", "INTERNATIONAL", "INTERNATION", "PUB", "PUBLIC"}
# Zkratky v názvech 13F → plné slovo (jak je píše seznam SEC).
_ABBR = {"INDS": "INDUSTRIES", "INDL": "INDUSTRIAL", "FINL": "FINANCIAL", "MNG": "MINING", "TECHNOLOGIE": "TECHNOLOGIES",
         "PHARMACEUTICALS": "PHARMACEUTICAL", "SVCS": "SERVICES", "COMMUNICATIONS": "COMMUNICATION", "MGMT": "MANAGEMENT",
         "BANCORPORATION": "BANCORP", "ENTMT": "ENTERTAINMENT", "SYS": "SYSTEMS", "LABS": "LABORATORIES"}


def norm_name(name: str) -> str:
    """„ASML HLDG NV“ i „ASML Holding N.V.“ → „ASML“ (shoda názvu emitenta napříč zdroji)."""
    words = [_ABBR.get(w, w) for w in re.sub(r"[^A-Z0-9 ]", " ", name.upper().replace("&", " AND ")).split()]
    while words and words[-1] in _SUFFIX:
        words.pop()
    return " ".join(words)


def ticker_by_name(names: dict[str, str], figi: dict, sec_names: dict[str, str]) -> dict[str, str]:
    """Náhradní ticker pro CUSIP, který OpenFIGI nezná (zahraniční CINS, chybný CUSIP ve výpisu):
    1) stejný emitent pod jiným, už namapovaným CUSIPem ve výpisech, 2) název v seznamu SEC
    (přesná shoda, jinak jednoznačná shoda začátku — 13F názvy bývají useknuté)."""
    known: dict[str, Counter] = {}
    for c, n in names.items():
        if figi.get(c):
            known.setdefault(norm_name(n), Counter())[figi[c]] += 1
    out = {}
    for c, n in names.items():
        if figi.get(c):
            continue
        k = norm_name(n)
        if len(k) < 2:
            continue
        if k in known:
            out[c] = known[k].most_common(1)[0][0]
        elif k in sec_names:
            out[c] = sec_names[k]
        elif len(k) >= 8:
            hits = {t for nm, t in sec_names.items() if nm.startswith(k) or (len(nm) >= 8 and k.startswith(nm))}
            if len(hits) == 1:
                out[c] = hits.pop()
    return out


# ── Sestavení snapshotu ──────────────────────────────────────────────────────

def build(funds_data: list[dict], figi: dict, stakes: list[dict]) -> dict:
    """funds_data: [{key, name, manager, style, cik, period, filed, prev_period, holdings, prev}]."""
    periods = Counter(f["period"] for f in funds_data if f.get("period"))
    quarter = periods.most_common(1)[0][0] if periods else None
    today = dt.date.today()

    def tick(c):
        return figi.get(c)

    out_funds, by_ticker = [], {}
    for f in funds_data:
        rows = compare(f["holdings"], f.get("prev"))
        for r in rows:
            r["ticker"] = tick(r["cusip"])
        stale = not f.get("period") or (today - dt.date.fromisoformat(f["period"])).days > STALE_DAYS \
            or (quarter and f["period"] < quarter and (dt.date.fromisoformat(quarter) - dt.date.fromisoformat(f["period"])).days > 100)
        held = [r for r in rows if r["action"] != "sold"]
        held.sort(key=lambda r: -r["value"])

        def pick(action, n=8):
            sel = [r for r in rows if r["action"] == action]
            sel.sort(key=lambda r: -abs(r.get("flow") or 0))
            return [{k: r.get(k) for k in ("ticker", "name", "value", "weight", "prev_weight", "chg_pct", "flow")}
                    for r in sel[:n]]

        out_funds.append({
            "key": f["key"], "name": f["name"], "manager": f["manager"], "style": f["style"], "cik": f["cik"],
            "period": f.get("period"), "filed": f.get("filed"), "prev_period": f.get("prev_period"), "stale": bool(stale),
            "total_value": round(sum(r["value"] for r in held)), "positions": len(held),
            "top": [{k: r.get(k) for k in ("ticker", "name", "value", "weight", "action", "chg_pct")} for r in held[:10]],
            "changes": {a: pick(a) for a in ("new", "added", "reduced", "sold")},
        })
        for r in rows:
            t = r["ticker"] or r["name"]
            e = by_ticker.setdefault(t, {"ticker": r["ticker"], "name": r["name"], "holders": [], "buyers": [],
                                         "sellers": [], "new": 0, "exits": 0, "buy_flow": 0, "sell_flow": 0,
                                         "value": 0})
            if r["action"] != "sold":
                e["holders"].append([f["key"], r["weight"]])
                e["value"] += r["value"]
            if stale:
                continue
            sig_now, sig_prev = r["weight"] >= SIGNIFICANT, r["prev_weight"] >= SIGNIFICANT
            if r["action"] in ("new", "added") and sig_now:
                e["buyers"].append([f["key"], r["action"], r["weight"], r.get("chg_pct")])
                e["buy_flow"] += r.get("flow") or 0
                e["new"] += r["action"] == "new"
            elif r["action"] in ("reduced", "sold") and sig_prev:
                e["sellers"].append([f["key"], r["action"], r["weight"], r.get("chg_pct")])
                e["sell_flow"] += -(r.get("flow") or 0)
                e["exits"] += r["action"] == "sold"

    names = {k: n for k, n, *_ in FUNDS}
    rows = list(by_ticker.values())
    for e in rows:
        e["holders"].sort(key=lambda x: -x[1])

    def slim(e, side):
        return {"ticker": e["ticker"], "name": e["name"], "holders": len(e["holders"]),
                "funds": e[side], "count": len(e[side]),
                "new" if side == "buyers" else "exits": e["new"] if side == "buyers" else e["exits"],
                "flow": round(e["buy_flow"] if side == "buyers" else e["sell_flow"])}

    buys = sorted((e for e in rows if e["buyers"]), key=lambda e: (-len(e["buyers"]), -e["buy_flow"]))[:30]
    sells = sorted((e for e in rows if e["sellers"]), key=lambda e: (-len(e["sellers"]), -e["sell_flow"]))[:30]
    held = sorted((e for e in rows if len(e["holders"]) >= 2),
                  key=lambda e: (-len(e["holders"]), -e["value"]))[:25]
    index = {e["ticker"]: {"n": e["name"], "h": e["holders"][:12], "hc": len(e["holders"]),
                           "b": e["buyers"], "s": e["sellers"]}
             for e in rows if e["ticker"] and (e["buyers"] or e["sellers"] or len(e["holders"]) >= 1)}
    return {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": "sec_13f",
        "quarter": quarter,
        "fund_names": names,
        "funds": out_funds,
        "consensus_buys": [slim(e, "buyers") for e in buys],
        "consensus_sells": [slim(e, "sellers") for e in sells],
        "most_held": [{"ticker": e["ticker"], "name": e["name"], "holders": len(e["holders"]),
                       "funds": e["holders"][:10], "value": round(e["value"])} for e in held],
        "stakes": stakes,
        "by_ticker": index,
        "note": "SEC 13F (čtvrtletní stav dlouhých pozic v US akciích, zveřejněno do 45 dnů) a 13D/13G "
                "(podíl nad 5 %, do 10 dnů). Bez shortů a opcí. Rozcestník, ne investiční doporučení.",
    }


def _scan(cache: dict) -> tuple[list[dict], list[dict]]:
    filings = cache.setdefault("filings", {})
    hdrs = cache.setdefault("stakes", {})
    figi = cache.setdefault("figi", {})
    funds_data, stakes, used = [], [], set()
    cutoff = (dt.date.today() - dt.timedelta(days=STAKE_DAYS)).isoformat()
    for key, name, manager, style, cik in FUNDS:
        r = _submissions(cik)
        if not r:
            print(f"  {name}: submissions nedostupné")
            continue
        f13 = [i for i, f in enumerate(r["form"]) if f == "13F-HR"]
        # nejnovější výpis za každé čtvrtletí (opožděný duplicitní výpis téhož období přeskočit)
        seen, picks = set(), []
        for i in f13:
            if r["reportDate"][i] not in seen:
                seen.add(r["reportDate"][i])
                picks.append(i)
            if len(picks) == 2:
                break
        loaded = []
        for i in picks:
            acc = r["accessionNumber"][i]
            used.add(acc)
            if acc not in filings:
                h = _load_13f(cik, acc)
                if h is None:
                    continue
                filings[acc] = {"period": r["reportDate"][i], "filed": r["filingDate"][i], "holdings": h}
            loaded.append(filings[acc])
        if loaded:
            cur, prev = loaded[0], loaded[1] if len(loaded) > 1 else None
            funds_data.append({"key": key, "name": name, "manager": manager, "style": style, "cik": cik,
                               "period": cur["period"], "filed": cur["filed"], "holdings": cur["holdings"],
                               "prev_period": prev["period"] if prev else None,
                               "prev": prev["holdings"] if prev else None})
            vs = f" (vs {prev['period']})" if prev else ""
            print(f"  {name}: {cur['period']} {len(cur['holdings'])} pozic{vs}")
        for i, form in enumerate(r["form"]):
            if r["filingDate"][i] < cutoff:
                break
            if not re.match(r"(SC |SCHEDULE )13[DG]", form):
                continue
            acc = r["accessionNumber"][i]
            if acc not in hdrs:
                hdrs[acc] = _stake(cik, acc, form, r["primaryDocument"][i]) or {"skip": True}
                hdrs[acc]["date"] = r["filingDate"][i]
            s = hdrs[acc]
            if not s.get("skip"):
                stakes.append({**s, "fund": key, "fund_name": name, "date": r["filingDate"][i],
                               "activist": "13D" in form, "amendment": form.endswith("/A")})
    # úklid cache: jen výpisy, které se ještě používají; hlavičky 13D/G jen z okna
    cache["filings"] = {a: v for a, v in filings.items() if a in used}
    cache["stakes"] = {a: v for a, v in hdrs.items() if v.get("date", "9") >= cutoff}

    cusips = sorted({c for f in funds_data for c in list(f["holdings"]) + list(f.get("prev") or {})})
    print(f"  CUSIPů {len(cusips)}, bez tickeru v cache {sum(1 for c in cusips if c not in figi)}")
    _figi(cusips, figi)
    figi_any = cache.setdefault("figi_any", {})
    _figi([c for c in cusips if c in figi and not figi[c]], figi_any, any_exchange=True)
    for c, t in figi_any.items():
        if t and not figi.get(c):
            figi[c] = t

    by_cik, by_name = _company_tickers()
    for s in stakes:
        s["ticker"] = by_cik.get(s.get("issuer_cik") or "")
    names = {c: h["name"] for f in funds_data for hs in (f.get("prev") or {}, f["holdings"]) for c, h in hs.items()}
    fallback = ticker_by_name(names, figi, by_name)
    print(f"  bez tickeru z OpenFIGI {sum(1 for c in cusips if not figi.get(c))}, dohledáno podle názvu {len(fallback)}")
    cache["name_tickers"] = fallback
    stakes.sort(key=lambda s: s["date"], reverse=True)
    return funds_data, stakes[:120]


def _push(base: str, payload: dict) -> None:
    token = os.environ.get("TRADEZER_TOKEN", "").strip()
    if not token:
        print("  --push přeskočen: chybí TRADEZER_TOKEN")
        return
    url = base.rstrip("/") + "/api/smart-money/funds/ingest"
    req = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode(), method="POST", headers={
        "Content-Type": "application/json", "X-Internal-Token": token, "User-Agent": "Tradezer-scan/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            print(f"  push -> {url}: {r.status} {r.read().decode()[:160]}")
    except urllib.error.HTTPError as e:
        print(f"  push FAIL {e.code}: {e.read().decode()[:200]}")
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"  push FAIL: {e}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Smart Money / Fondy — SEC 13F + 13D/13G")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--base", default=os.environ.get("TRADEZER_BASE_URL", "https://tradezer.app"))
    ap.add_argument("--no-file", action="store_true")
    args = ap.parse_args()
    try:
        cache = json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    print(f"Fondy: {len(FUNDS)} fondů, SEC 13F + 13D/13G…")
    funds_data, stakes = _scan(cache)
    tmp = CACHE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache), encoding="utf-8")
    os.replace(tmp, CACHE)
    out = build(funds_data, {**cache["figi"], **{c: t for c, t in cache.get("name_tickers", {}).items()
                                                  if not cache["figi"].get(c)}}, stakes)
    print(f"  {len(out['funds'])} fondů (čtvrtletí {out['quarter']}), konsenzus nákupů {len(out['consensus_buys'])}, "
          f"13D/G {len(stakes)}, tickerů {len(out['by_ticker'])}")
    if not args.no_file:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        print(f"-> {OUT}")
    if args.push:
        _push(args.base, out)


if __name__ == "__main__":
    main()
