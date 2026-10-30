#!/usr/bin/env python3
"""Earnings watch (Spark): hlídá výsledky hospodaření firem z Valuation radaru, lokálním modelem
na Sparku (gpt-oss přes LiteLLM bránu) je co nejdřív vysvětlí a hotové texty pošle do Tradezeru.

Zdroj: SEC EDGAR — firma musí výsledky do pár minut po vydání tiskové zprávy podat jako 8-K
(Item 2.02, tisková zpráva = exhibit 99.1). Konsenzus EPS: Nasdaq earnings kalendář.
Reakce ceny: Yahoo chart (5m vč. pre/after-hours) — průběžně 30 h po zveřejnění.

Nezatěžuje Neon: stav (viděné filingy) drží lokálně v JSON, do DB jde jen přes API při novém reportu.

Spuštění (systemd, appvenv kvůli httpx):
  EnvironmentFile=~/tradezer/scans.env  (TRADEZER_TOKEN, volitelně TRADEZER_BASE_URL)
  EnvironmentFile=~/tradezer/predictor.env  (LLM_BASE_URL, LLM_API_KEY, LLM_MODEL=heavy)
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
LLM_BASE = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:4000/v1").rstrip("/")
LLM_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "heavy")
LLM_EFFORT = os.environ.get("EARNINGS_REASONING", "high")   # gpt-oss: víc přemýšlení = méně chyb v číslech
MAX_PRESS_CHARS = 45_000
ANALYSIS_TRIES = 3          # pak se report uloží i bez analýzy a doplní se v dalších cyklech

EXTRACT_SYSTEM = (
    "Jsi finanční analytik. Dostaneš text tiskové zprávy o výsledcích hospodaření americké firmy "
    "(SEC 8-K, exhibit 99.1) a konsenzus odhadu EPS analytiků. Vrať POUZE validní JSON (bez markdownu):\n"
    "{\n"
    '  "fiscal_period": string|null,      // např. "Q3 2026"\n'
    '  "revenue_usd": number|null,        // celkové tržby za čtvrtletí v USD (např. 102300000000)\n'
    '  "revenue_yoy_pct": number|null,    // meziroční růst tržeb v %, jen pokud je v textu nebo jde přímo odečíst\n'
    '  "eps_gaap": number|null,           // zředěný EPS za čtvrtletí podle GAAP (diluted EPS)\n'
    '  "eps_adjusted": number|null,       // upravený EPS (non-GAAP / adjusted), JEN pokud ho firma v textu uvádí\n'
    '  "verdict": "positive"|"negative"|"mixed"|"neutral",\n'
    '  "headline_cs": string,             // 1 věta česky: co je hlavní zpráva\n'
    '  "summary_cs": [string],            // 3–5 odrážek česky: co se stalo a co to znamená pro firmu\n'
    '  "guidance_cs": string|null         // výhled vedení na další období, pokud ho zpráva obsahuje\n'
    "}\n"
    "Pravidla: čísla ber VÝHRADNĚ z dodaného textu, nic nedopočítávej ani neodhaduj — co v textu není, dej null. "
    "Verdikt hodnotí zprávu fundamentálně (růst, marže, zisk vs. konsenzus, výhled, jednorázové vlivy). "
    "Když jsou dobré tržby, ale zisk pod odhadem (nebo naopak), je to 'mixed'. "
    "Konsenzus EPS analytiků bývá na upraveném (non-GAAP) základu, pokud ho firma vykazuje — porovnávej se správným "
    "číslem a jednorázové položky (zisky/ztráty z investic, restrukturalizace) výslovně zmiň. "
    "Než napíšeš 'nad/pod odhadem', porovnej čísla: vyšší EPS než konsenzus = překonal odhad. "
    "headline_cs je JEDNA jasná věta bez závorek a bez oprav sebe sama; když zmiňuje zisk na akcii, uveď "
    "skutečné číslo i odhad (např. „zisk na akcii 0,18 USD proti odhadu 0,17 USD“). "
    "Jednorázové položky (zisky/ztráty z investic, odpisy výzkumu IPR&D, restrukturalizace, srovnání s loňským "
    "jednorázovým ziskem), pokud je zpráva obsahuje, popiš v samostatné odrážce s částkou a správnou jednotkou "
    "(USD na akcii ≠ mld. USD) a s tím, jak ovlivnily zisk na akcii. "
    "Procenta růstu ber přesně z textu a uveď, čeho se týkají (celkové tržby vs. produkty vs. segment). "
    "Piš spisovnou češtinou srozumitelně pro retailového tradera, bez anglických zkratek kde to jde; "
    "částky piš jako „102,3 mld. USD“. "
    "NIKDY nedoporučuj nákup ani prodej akcie."
)

REACTION_SYSTEM = (
    "Jsi finanční analytik. Dostaneš shrnutí výsledků hospodaření firmy, reakci ceny akcie po zveřejnění "
    "a titulky zpráv, které po zveřejnění vyšly. Napiš spisovnou češtinou 2–4 krátké odrážky (každá začíná \"- \"), "
    "PROČ trh reaguje tak, jak reaguje (co investoři nejspíš řeší: zisk vs. odhad, výhled, výdaje, "
    "konkrétní segment…). Opírej se jen o dodané informace; když z nich důvod nejde poznat, řekni to. "
    "Chybějící výhled NEBER jako důvod — řada firem (např. Alphabet) výhled vůbec nedává. "
    "Pokud zisk ovlivnila jednorázová položka, zmiň ji. Nevymýšlej čísla, která v podkladech nejsou. "
    "Každá odrážka max 35 slov. Odpovídej VÝHRADNĚ česky. "
    "NIKDY nedoporučuj nákup ani prodej. Odpověz jen odrážkami."
)

_CZ = re.compile(r"[áčďéěíňóřšťúůýž]", re.I)


def is_czech(text: str) -> bool:
    return len(_CZ.findall(text or "")) >= max(3, len(text or "") // 150)


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


# ------------------------------------------------------------------ lokální LLM (Spark)

def llm(system: str, user: str, max_tokens: int) -> str | None:
    """gpt-oss přes LiteLLM bránu na Sparku. Reasoning spotřebuje část max_tokens → dávat s rezervou."""
    try:
        r = httpx.post(f"{LLM_BASE}/chat/completions", timeout=600,
                       headers={"Authorization": f"Bearer {LLM_KEY}"} if LLM_KEY else {},
                       json={"model": LLM_MODEL, "temperature": 0.2, "max_tokens": max_tokens,
                             "reasoning_effort": LLM_EFFORT,
                             "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
        r.raise_for_status()
        txt = (r.json()["choices"][0]["message"]["content"] or "").strip()
        return txt.split("</think>")[-1].strip() or None
    except Exception as e:  # noqa: BLE001
        log("LLM fail", str(e)[:200])
        return None


def analyze(ticker: str, press_text: str, eps: dict) -> dict | None:
    est = eps.get("eps_estimate")
    cons = (f"Konsenzus EPS analytiků: {est} (počet odhadů: {eps.get('n_estimates')})" if est is not None
            else "Konsenzus EPS: není k dispozici")
    user = f"Firma: {ticker}\n{cons}\n\nTisková zpráva:\n{press_text[:MAX_PRESS_CHARS]}"
    for attempt in range(2):
        txt = llm(EXTRACT_SYSTEM, user if not attempt else user + "\n\nOdpověz česky.", 12000)
        m = re.search(r"\{.*\}", txt or "", flags=re.S)
        try:
            data = json.loads(m.group(0)) if m else None
        except ValueError:
            data = None
        if isinstance(data, dict) and data.get("headline_cs") and is_czech(
                data["headline_cs"] + " ".join(map(str, data.get("summary_cs") or []))):
            return data
        log("analysis unreadable / not Czech", ticker, (txt or "")[:160])
    return None


def explain(c: dict) -> str | None:
    news = "\n".join(f"- {t}" for t in c.get("news") or []) or "(žádné titulky)"
    eps = (f"EPS {c['eps_actual']} vs. konsenzus {c['eps_estimate']}"
           if c.get("eps_actual") is not None and c.get("eps_estimate") is not None else "EPS vs. konsenzus: neznámé")
    user = (f"Firma: {c['name']} ({c['ticker']})\nObdobí: {c.get('fiscal_period') or '?'}\n"
            f"Shrnutí výsledků:\n{c.get('headline_cs') or ''}\n{c.get('summary_cs') or ''}\n{eps}\n"
            f"Výhled: {c.get('guidance_cs') or 'neuveden'}\n"
            f"Reakce ceny od zveřejnění: {c['reaction_pct']:+.2f} %\n\nTitulky po zveřejnění:\n{news}")
    for attempt in range(2):
        txt = llm(REACTION_SYSTEM, user if not attempt else user + "\n\nOdpověz česky.", 8000)
        lines = [ln.strip() for ln in (txt or "").splitlines() if ln.strip().startswith(("-", "•", "*"))]
        out = "\n".join("- " + ln.lstrip("-•* ").strip() for ln in lines)
        if out and is_czech(out):
            return out
        log("explanation not Czech", c["ticker"], (txt or "")[:120])
    return None


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
                ingest(st, t, cik, f)
            except Exception as e:  # noqa: BLE001
                log("ingest fail", t, f["accession"], str(e)[:200])


def ingest(st: dict, t: str, cik: int, f: dict) -> None:
    """Tisková zpráva → analýza gpt-oss → Tradezer. Když model selže, zkusí to v dalších cyklech;
    po ANALYSIS_TRIES uloží report bez analýzy (ať je vidět aspoň odkaz) a doplňuje ji dál."""
    acc = f["accession"]
    pend = st.setdefault("pending", {}).setdefault(acc, {"tries": 0})
    text, url = press_release(cik, acc, f["primary"])
    eps = nasdaq_eps(t, f["accepted_at"])
    t0 = time.time()
    data = analyze(t, text, eps)
    pend["tries"] += 1
    if data is None and pend["tries"] < ANALYSIS_TRIES:
        save_state(st)
        return
    res = api("POST", "/api/valuation/earnings/ingest", json={
        "ticker": t, "accession": acc, "accepted_at": f["accepted_at"].isoformat(), "url": url,
        "analysis": data, "llm_model": f"spark-{LLM_MODEL}" if data else None, **eps})
    st["seen"][acc] = res["id"]
    st["watch"][str(res["id"])] = {"ticker": t, "accepted_at": f["accepted_at"].isoformat(), "last": 0,
                                   "cik": cik, "accession": acc, "primary": f["primary"]}
    st["pending"].pop(acc, None)
    save_state(st)
    log("EARNINGS", t, acc, res, f"llm {time.time() - t0:.0f}s")


def reanalyze(st: dict, w: dict) -> None:
    """Report uložený bez analýzy (model tehdy selhal) → zkusit znovu."""
    text, url = press_release(w["cik"], w["accession"], w["primary"])
    acc_at = datetime.fromisoformat(w["accepted_at"])
    eps = nasdaq_eps(w["ticker"], acc_at)
    data = analyze(w["ticker"], text, eps)
    if data:
        res = api("POST", "/api/valuation/earnings/ingest", json={
            "ticker": w["ticker"], "accession": w["accession"], "accepted_at": w["accepted_at"], "url": url,
            "analysis": data, "llm_model": f"spark-{LLM_MODEL}", **eps})
        log("reanalyzed", w["ticker"], res)


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
                ctx = res.pop("explain", None)
                log("reaction", w["ticker"], res)
                if not res.get("analyzed") and w.get("accession"):
                    reanalyze(st, w)
                if ctx:
                    text = explain(ctx)
                    if text:
                        api("POST", f"/api/valuation/earnings/{rid}/explanation", json={"reaction_cs": text})
                        log("explained", w["ticker"])
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
