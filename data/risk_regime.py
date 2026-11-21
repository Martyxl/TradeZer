"""Režim trhu: klid / stabilizace / napětí / panika — pro dashboard a ochranu fondu.

Tři vrstvy (jen stdlib, běží na Sparku nebo z rezidenční IP; Yahoo blokuje datacentra):
  1. TRŽNÍ UKAZATELE (Yahoo, denní close): VIX, S&P 500, Nasdaq-100, ropa, zlato, výnos US10Y.
  2. DETERMINISTICKÁ KLASIFIKACE `classify()` — transparentní prahy, žádná magie.
     panic      = VIX ≥ 30 / S&P −3 % za den / pokles ≥ 8 % od 20denního maxima
     tension    = VIX ≥ 22 / VIX +25 % za 5 dní / S&P −3 % za 5 dní / ropa +10 % / …
     recovering = po nedávném šoku se trh STABILIZUJE (VIX klesl ≥ 15 % od vrcholu, S&P bez
                  nových minim) → nakupovat se smí, ale po částech
     calm       = nic z výše uvedeného
  3. GEOPOLITIKA: titulky ze světových RSS ohodnotí lokální LLM (Spark gpt-oss) 0–3.
     Závažnost ≥ 2 zvedne klid na napětí; 3 + tržní napětí = panika. Samotná zpráva bez
     potvrzení trhem nikdy nespustí paniku (vyhýbáme se přehnané reakci na titulky).

Použití:
  TRADEZER_TOKEN=... py risk_regime.py --push            # jednorázově
  TRADEZER_TOKEN=... python3 risk_regime.py --push --loop 60   # Spark: každou hodinu
  py risk_regime.py --no-llm                             # jen tržní ukazatele, vytiskne
Fond importuje `get_regime()` (čte cache soubor, jinak spočítá živě).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

BASE = os.environ.get("TRADEZER_BASE_URL", "https://tradezer.app").rstrip("/")
TOKEN = os.environ.get("TRADEZER_TOKEN", "").strip()
CACHE = os.environ.get("REGIME_CACHE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "regime_cache.json"))
LLM_BASE = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:4000/v1").rstrip("/")
LLM_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "heavy")
UA = "Mozilla/5.0 TradezerRegime/1.0"

SYMBOLS = {"vix": "^VIX", "spx": "^GSPC", "ndx": "^NDX", "oil": "CL=F", "gold": "GC=F", "us10y": "^TNX"}

LABELS = {"calm": "Klid", "recovering": "Stabilizace", "tension": "Napětí", "panic": "Panika"}
POLICY = {
    "calm": "Běžný režim — fond nakupuje podle konvikce.",
    "recovering": "Trh se po šoku stabilizuje — nákupy jen po částech (půlka cílové váhy).",
    "tension": "Zvýšené napětí — jen nejsilnější příležitosti a po částech, ostatní počkají.",
    "panic": "Panika — fond nenakupuje a čeká na stabilizaci. Neprodává (nechceme platit daň ze zisku).",
}


# ── 1. Tržní ukazatele ───────────────────────────────────────────────────────
def _get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def yahoo_closes(sym: str, rng: str = "3mo") -> list[float]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range={rng}&interval=1d"
    j = json.loads(_get(url))
    res = (j.get("chart") or {}).get("result") or []
    if not res:
        return []
    closes = (((res[0].get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
    return [c for c in closes if c is not None]


def _chg(arr: list[float], n: int) -> float | None:
    """Změna v % oproti n obchodním dnům zpět."""
    if len(arr) <= n or not arr[-1 - n]:
        return None
    return (arr[-1] / arr[-1 - n] - 1) * 100


def compute_indicators(series: dict[str, list[float]]) -> dict:
    """Z denních close řad spočítá ukazatele pro classify(). Chybějící řada → None."""
    ind: dict = {}
    vix, spx = series.get("vix") or [], series.get("spx") or []
    if vix:
        ind["vix"] = vix[-1]
        ind["vix_chg_1d"], ind["vix_chg_5d"] = _chg(vix, 1), _chg(vix, 5)
        peak = max(vix[-10:])
        ind["vix_peak10"] = peak
        ind["vix_recovery"] = (1 - vix[-1] / peak) if peak else 0.0
    if spx:
        ind["spx"] = spx[-1]
        ind["spx_chg_1d"], ind["spx_chg_5d"] = _chg(spx, 1), _chg(spx, 5)
        ind["spx_dd_20d"] = (spx[-1] / max(spx[-20:]) - 1) * 100
        ind["spx_dd_10d"] = (spx[-1] / max(spx[-10:]) - 1) * 100
        # „netvoří nová minima": poslední close je nad nejnižším close z 5 dní PŘED ním
        ind["spx_above_5d_low"] = len(spx) > 6 and spx[-1] > min(spx[-6:-1])
    if series.get("ndx"):
        ind["ndx_chg_1d"], ind["ndx_chg_5d"] = _chg(series["ndx"], 1), _chg(series["ndx"], 5)
    if series.get("oil"):
        ind["oil"], ind["oil_chg_5d"] = series["oil"][-1], _chg(series["oil"], 5)
    if series.get("gold"):
        ind["gold"], ind["gold_chg_5d"] = series["gold"][-1], _chg(series["gold"], 5)
    if series.get("us10y"):
        ind["us10y"] = series["us10y"][-1]
        ind["us10y_chg_5d"] = round(series["us10y"][-1] - series["us10y"][-6], 3) if len(series["us10y"]) > 5 else None
    return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in ind.items()}


# ── 2. Klasifikace ───────────────────────────────────────────────────────────
def classify(ind: dict, geo_sev: int | None = None) -> dict:
    """Čistá funkce: ukazatele (+ volitelně závažnost geopolitiky 0–3) → {state, label, reasons}."""
    g = lambda k: ind.get(k)  # noqa: E731
    vix = g("vix")
    panic, tension = [], []
    if vix is not None and vix >= 30:
        panic.append(f"VIX {vix:.1f} je nad 30 (extrémní strach)")
    if g("spx_chg_1d") is not None and g("spx_chg_1d") <= -3:
        panic.append(f"S&P 500 klesl za den o {abs(g('spx_chg_1d')):.1f} %")
    if g("spx_dd_20d") is not None and g("spx_dd_20d") <= -8:
        panic.append(f"S&P 500 je {abs(g('spx_dd_20d')):.1f} % pod 20denním maximem")
    if vix is not None and 22 <= vix < 30:
        tension.append(f"VIX {vix:.1f} je zvýšený (nad 22)")
    if g("vix_chg_5d") is not None and g("vix_chg_5d") >= 25 and (vix or 0) >= 18:
        tension.append(f"VIX vyskočil za 5 dní o {g('vix_chg_5d'):.0f} %")
    if g("spx_chg_5d") is not None and g("spx_chg_5d") <= -3:
        tension.append(f"S&P 500 za 5 dní {g('spx_chg_5d'):+.1f} %")
    if g("spx_dd_20d") is not None and -8 < g("spx_dd_20d") <= -5:
        tension.append(f"S&P 500 je {abs(g('spx_dd_20d')):.1f} % pod 20denním maximem")
    if g("oil_chg_5d") is not None and g("oil_chg_5d") >= 10:
        tension.append(f"ropa za 5 dní {g('oil_chg_5d'):+.0f} % (šok z nabídky/geopolitiky)")
    if g("gold_chg_5d") is not None and g("gold_chg_5d") >= 4 and (vix or 0) >= 18:
        tension.append(f"zlato za 5 dní {g('gold_chg_5d'):+.1f} % (útěk do bezpečí)")

    market = "panic" if panic else ("tension" if tension else "calm")
    reasons = panic + tension
    state = market

    # Stabilizace po šoku: nedávný šok (VIX ≥ 30 v posledních 10 dnech / S&P −6 % od 10d maxima)
    shock = ((g("vix_peak10") or 0) >= 30) or ((g("spx_dd_10d") or 0) <= -6)
    stabilized = (vix is not None and (g("vix_recovery") or 0) >= 0.15 and vix < 28
                  and bool(g("spx_above_5d_low")))
    if market != "panic" and shock:
        if stabilized:
            state = "recovering"
            reasons = [f"po šoku (VIX max {g('vix_peak10'):.0f} → {vix:.0f}) se trh stabilizuje: "
                       f"VIX klesl o {g('vix_recovery') * 100:.0f} % od vrcholu a S&P netvoří nová minima"]
        elif market == "calm":
            state = "tension"
            reasons = ["nedávný šok na trhu a zatím bez potvrzené stabilizace"]

    # Geopolitika (LLM): sama o sobě nanejvýš napětí; panika jen s potvrzením trhem
    if geo_sev is not None and geo_sev >= 2:
        if state in ("calm", "recovering"):
            state = "tension"
        if geo_sev >= 3 and market == "tension":
            state = "panic"
        reasons.append(f"geopolitika: závažnost {geo_sev}/3 podle hodnocení světových titulků")
    if state == "calm" and not reasons:
        reasons = ["žádný z ukazatelů napětí nepřekračuje práh"]
    return {"state": state, "label": LABELS[state], "policy": POLICY[state], "reasons": reasons,
            "market_state": market}


# ── 3. Geopolitika: titulky + LLM ────────────────────────────────────────────
FEEDS = [
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("The Guardian", "https://www.theguardian.com/world/rss"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("CNBC World", "https://www.cnbc.com/id/100727362/device/rss/rss.html"),
]
_GEO = re.compile(
    r"\b(iran\w*|israel\w*|gaza|hezbollah|hamas|houthis?|hormuz|red sea|nuclear|missiles?|"
    r"air ?strikes?|ceasefire|cease-fire|geopolit\w*|escalat\w*|sanctions?|invasion|invade\w*|"
    r"taiwan|ukrain\w*|russia\w*|north korea|middle east|opec\+?|brent|crude|china|war|troops|"
    r"attack\w*|threat\w*)\b", re.I)


def fetch_headlines(limit_per_feed: int = 25) -> list[dict]:
    out = []
    for name, url in FEEDS:
        try:
            root = ET.fromstring(_get(url, 15))
        except Exception as e:  # noqa: BLE001 — jeden výpadek feedu nevadí
            print(f"  feed {name}: {e}")
            continue
        for it in list(root.iter("item"))[:limit_per_feed]:
            title = (it.findtext("title") or "").strip()
            if title and _GEO.search(title):
                out.append({"title": title, "source": name})
    seen, uniq = set(), []
    for h in out:
        k = re.sub(r"\W+", " ", h["title"].lower())[:80]
        if k not in seen:
            seen.add(k)
            uniq.append(h)
    return uniq[:30]


GEO_SYSTEM = (
    "Jsi analytik makro rizika pro investiční fond s horizontem 3+ roky. Z titulků světových zpráv "
    "posuď, jak MOC vážně hrozí šok pro finanční trhy. Škála 0–3: 0 = šum / běžné dění; 1 = pozor, "
    "napětí bez přímého dopadu na trhy; 2 = vážné riziko (reálná eskalace, hrozba pro dodávky ropy, "
    "přímý střet států, vyhrožování jadernou zbraní); 3 = extrémní šok (použití jaderné zbraně, přímá "
    "válka velmocí, uzavření Hormuzu). Slovní výhrůžky bez činů dávej obvykle 1–2. NEPŘEHÁNĚJ. "
    "DŮLEŽITÉ: dlouhodobě trvající konflikty (válka na Ukrajině, Gaza, Houthiové) jsou už zahrnuté "
    "v cenách — bez NOVÉ, náhlé eskalace je hodnoť 0–1. Vyšší hodnotu dej jen za něco nového a "
    "výrazně horšího než dosavadní stav. "
    'Odpověz POUZE JSON: {"severity": 0-3, "summary": "1–2 krátké české věty", "headlines": '
    '[{"i": číslo titulku, "severity": 0-3, "why": "max 12 slov česky"}]} (max 4 nejzávažnější).'
)


def _parse_geo(text: str) -> dict | None:
    """Přijme jen CELÝ objekt se `severity` i `summary` — useknutá odpověď (limit tokenů) nesmí
    projít přes vnořený objekt jednoho titulku."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```")[1]
        t = t[4:] if t[:4].lower() == "json" else t
    a, b = t.find("{"), t.rfind("}")
    if a == -1 or b <= a:
        return None
    try:
        j = json.loads(t[a:b + 1])
    except ValueError:
        return None
    return j if isinstance(j, dict) and "severity" in j and "summary" in j else None


def llm_geo(headlines: list[dict]) -> dict | None:
    if not headlines or not LLM_KEY and "127.0.0.1" not in LLM_BASE:
        return None
    body = {"model": LLM_MODEL, "temperature": 0, "max_tokens": 3000,
            "messages": [{"role": "system", "content": GEO_SYSTEM},
                         {"role": "user", "content": "\n".join(f"{i}. [{h['source']}] {h['title']}"
                                                                for i, h in enumerate(headlines))}]}
    req = urllib.request.Request(f"{LLM_BASE}/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": f"Bearer {LLM_KEY}"} if LLM_KEY else {})})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            text = json.loads(r.read().decode())["choices"][0]["message"]["content"] or ""
    except Exception as e:  # noqa: BLE001
        print(f"  LLM geo selhalo: {e}")
        return None
    j = _parse_geo(text)
    try:
        sev = int(j["severity"])
    except (TypeError, KeyError, ValueError):
        print(f"  LLM geo: nečitelná/useknutá odpověď {text[:120]!r}")
        return None
    sev = max(0, min(3, sev))
    tops = []
    for h in (j.get("headlines") or [])[:5]:
        try:
            src = headlines[int(h["i"])]
            tops.append({"title": src["title"], "source": src["source"],
                         "severity": max(0, min(3, int(h.get("severity", 0)))), "why": str(h.get("why", ""))[:200]})
        except (KeyError, ValueError, IndexError, TypeError):
            continue
    return {"severity": sev, "summary": str(j.get("summary", ""))[:400], "headlines": tops,
            "n_headlines": len(headlines), "model": LLM_MODEL}


# ── Sestavení + push + cache ─────────────────────────────────────────────────
# ── 4. Sentiment trhu (strach ↔ chamtivost, 0–100) ─────────────────────────
# Pět tržních složek, každá převedená na percentil vůči posledním 252 obchodním dnům
# (0 = nejvíc strachu za rok, 100 = nejvíc chamtivosti); skóre = průměr. Zprávy ani
# predikce do toho NEjdou (prediktor je historicky medvědí → zkreslil by to).
SENT_SYMBOLS = {"spx": "^GSPC", "vix": "^VIX", "vix3m": "^VIX3M", "tlt": "TLT", "hyg": "HYG", "ief": "IEF"}
SENT_PARTS = [
    ("vix50", "VIX vs. 50denní průměr", "volatilita proti normálu"),
    ("term", "Struktura VIX (VIX / VIX3M)", "nad 1 = panika teď, ne za 3 měsíce"),
    ("mom", "S&P 500 vs. 125denní průměr", "momentum trhu"),
    ("haven", "Akcie vs. dluhopisy (20 dní)", "útěk do bezpečí"),
    ("junk", "Rizikové vs. státní dluhopisy (20 dní)", "chuť na riziko u kreditu"),
]
SENT_BANDS = [(20, "extreme_fear", "Extrémní strach"), (40, "fear", "Strach"), (60, "neutral", "Neutrál"),
              (80, "greed", "Chamtivost"), (101, "extreme_greed", "Extrémní chamtivost")]
# Historie 11/2011–11/2026 (Yahoo denní data, Nasdaq-100): co následovalo po dni v pásmu.
# next_day_move = průměrný |pohyb| další den vůči běžnému dni; up = podíl dní nahoru;
# fwd20 = průměrný výnos NDX za 20 obchodních dní, pos20 = podíl kladných.
SENT_HISTORY = {
    "extreme_fear": {"next_day_move": 1.8, "up": 58, "fwd20": 2.4, "pos20": 67, "p10_20": -6.5},
    "fear": {"next_day_move": 1.1, "up": 56, "fwd20": 1.6, "pos20": 70},
    "neutral": {"next_day_move": 0.9, "up": 56, "fwd20": 1.4, "pos20": 67},
    "greed": {"next_day_move": 0.8, "up": 54, "fwd20": 1.2, "pos20": 65},
    "extreme_greed": {"next_day_move": 0.6, "up": 58, "fwd20": 1.0, "pos20": 65},
    "all": {"up": 56, "fwd20": 1.5, "pos20": 67},
}


def yahoo_daily(sym: str, rng: str = "2y") -> dict:
    """{datum: close} — po datech, aby šly řady různých symbolů spolehlivě zarovnat."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range={rng}&interval=1d"
    res = ((json.loads(_get(url)).get("chart") or {}).get("result") or [{}])[0]
    ts = res.get("timestamp") or []
    closes = (((res.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
    return {datetime.fromtimestamp(t, timezone.utc).date().isoformat(): c for t, c in zip(ts, closes) if c}


def sentiment_from_series(s: dict[str, dict]) -> dict | None:
    """Skóre 0–100 ze zarovnaných denních řad (klíče SENT_SYMBOLS). None = málo dat."""
    days = sorted(set.intersection(*[set(v) for v in s.values()])) if s and all(s.values()) else []
    if len(days) < 260:
        return None
    c = {k: [s[k][d] for d in days] for k in s}

    def r20(a, i):
        return a[i] / a[i - 20] - 1

    raw: dict[str, list] = {k: [] for k, _, _ in SENT_PARTS}
    for i in range(len(days)):
        if i < 125:
            for k in raw:
                raw[k].append(None)
            continue
        raw["vix50"].append(-(c["vix"][i] / (sum(c["vix"][i - 50:i]) / 50) - 1))
        raw["term"].append(-(c["vix"][i] / c["vix3m"][i]))
        raw["mom"].append(c["spx"][i] / (sum(c["spx"][i - 125:i]) / 125) - 1)
        raw["haven"].append(r20(c["spx"], i) - r20(c["tlt"], i))
        raw["junk"].append(r20(c["hyg"], i) - r20(c["ief"], i))
    last = len(days) - 1

    def pct(series):
        w = [x for x in series[max(0, last - 252):last + 1] if x is not None]
        return round(100 * sum(1 for x in w if x <= series[last]) / len(w)) if len(w) >= 120 else None

    parts = []
    for key, label, hint in SENT_PARTS:
        v = pct(raw[key])
        if v is not None:
            parts.append({"key": key, "label": label, "hint": hint, "value": v})
    if len(parts) < 4:
        return None
    score = round(sum(p["value"] for p in parts) / len(parts))
    band = next(b for b in SENT_BANDS if score < b[0])
    vix, vix3m = c["vix"][last], c["vix3m"][last]
    return {"score": score, "band": band[1], "label": band[2], "parts": parts, "as_of_date": days[-1],
            "vix": round(vix, 2), "vix_term": round(vix / vix3m, 3), "backwardation": vix > vix3m,
            "history": SENT_HISTORY[band[1]], "history_all": SENT_HISTORY["all"]}


def compute_sentiment() -> dict | None:
    series = {}
    for key, sym in SENT_SYMBOLS.items():
        try:
            series[key] = yahoo_daily(sym)
        except Exception as e:  # noqa: BLE001
            print(f"  sentiment {sym}: {e}")
            return None
        time.sleep(0.2)
    return sentiment_from_series(series)


def compute_regime(use_llm: bool = True, prev_geo: dict | None = None) -> dict:
    series = {}
    for key, sym in SYMBOLS.items():
        try:
            series[key] = yahoo_closes(sym)
        except Exception as e:  # noqa: BLE001
            print(f"  {sym}: {e}")
            series[key] = []
        time.sleep(0.2)
    ind = compute_indicators(series)
    geo = prev_geo
    if use_llm:
        fresh = llm_geo(fetch_headlines())
        geo = fresh or prev_geo
    sev = geo.get("severity") if geo else None
    out = classify(ind, sev)
    try:
        sent = compute_sentiment()
    except Exception as e:  # noqa: BLE001
        print(f"  sentiment: {e}")
        sent = None
    out.update(indicators=ind, geo=geo, sentiment=sent, as_of=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    return out


def _read_cache() -> dict | None:
    try:
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write_cache(r: dict) -> None:
    try:
        with open(CACHE, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False)
    except OSError as e:
        print(f"  cache nezapsána: {e}")


def get_regime(max_age_min: int = 180) -> dict:
    """Pro fond: čerstvá cache ze skeneru, jinak živý výpočet (bez LLM; geo ze staré cache)."""
    c = _read_cache()
    if c and c.get("as_of"):
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(c["as_of"])).total_seconds() / 60
            if age <= max_age_min:
                return c
        except ValueError:
            pass
    r = compute_regime(use_llm=False, prev_geo=(c or {}).get("geo"))
    _write_cache(r)
    return r


def push(r: dict) -> None:
    req = urllib.request.Request(f"{BASE}/api/regime/ingest", data=json.dumps(r).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Internal-Token": TOKEN, "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            print(f"  push OK: {resp.read().decode()[:100]}")
    except urllib.error.HTTPError as e:
        print(f"  push HTTP {e.code}: {e.read().decode()[:160]}")
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"  push fail: {e}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--loop", type=int, default=0, help="opakuj každých N minut")
    ap.add_argument("--geo-every", type=int, default=120, help="LLM hodnocení titulků nejvýš každých N minut")
    args = ap.parse_args()
    if args.push and not TOKEN:
        sys.exit("Chybí TRADEZER_TOKEN.")
    last_geo_at = 0.0
    geo = (_read_cache() or {}).get("geo")
    while True:
        use_llm = not args.no_llm and (time.time() - last_geo_at) >= args.geo_every * 60
        r = compute_regime(use_llm=use_llm, prev_geo=geo)
        if use_llm:
            last_geo_at = time.time()
        geo = r.get("geo")
        _write_cache(r)
        print(f"[{time.strftime('%Y-%m-%d %H:%M')}] režim: {r['label']} | VIX {r['indicators'].get('vix')} | "
              f"geo {(geo or {}).get('severity')} | {'; '.join(r['reasons'])}")
        if args.push:
            push(r)
        if args.loop <= 0:
            if not args.push:
                print(json.dumps(r, ensure_ascii=False, indent=2))
            return
        time.sleep(args.loop * 60)


if __name__ == "__main__":
    main()
