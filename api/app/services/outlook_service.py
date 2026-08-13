"""Pre-open výhled: scénáře dopadu dnešních plánovaných US eventů na instrumenty.

Deterministický rule engine (typ eventu × instrument → směr + intenzita pro
hot/inline/cool výsledek). LLM přidává jen krátký narativ dne (viz llm_client).
Není investiční doporučení — edukativní mapování makro reakcí.
"""
from __future__ import annotations

from datetime import datetime, timezone

import structlog

from app.sources.forex_factory import get_upcoming_events

log = structlog.get_logger(__name__)

# Instrumenty citlivé na sazby (akciové indexy) a jejich relativní citlivost.
# NQ (tech, dlouhá durace) reaguje nejvíc, YM (value/průmysl) nejmíň.
INDEX_SENSITIVITY = {"NQ": 1.0, "ES": 0.8, "YM": 0.65}
GOLD_SYMBOLS = {"XAUUSD", "GOLD"}

# Kategorie eventu → (znaménko pro indexy, znaménko pro gold) při výsledku NAD
# forecastem (hot). Cool = opačné znaménko. + = nahoru, − = dolů, 0 = neutrálně.
# label = makro zdůvodnění pro hot směr.
_CATEGORIES: dict[str, dict] = {
    "inflation": {"index": -1, "gold": -1,
                  "hot": "vyšší inflace → jestřábí Fed (sazby výš)",
                  "cool": "nižší inflace → holubičí Fed (prostor pro nižší sazby)"},
    "wages": {"index": -1, "gold": -1,
              "hot": "silnější mzdy → inflační tlak → jestřábí",
              "cool": "slabší mzdy → uvolnění inflačního tlaku → holubičí"},
    "rates": {"index": -1, "gold": -1,
              "hot": "jestřábí sazby / rétorika",
              "cool": "holubičí sazby / rétorika"},
    "jobs": {"index": -1, "gold": -1,
             "hot": "silný trh práce → jestřábí (good-news-is-bad-news)",
             "cool": "slabší trh práce → holubičí"},
    "claims": {"index": 1, "gold": 1,
               "hot": "více žádostí o podporu → slabší trh práce → holubičí",
               "cool": "méně žádostí → silnější trh práce → jestřábí"},
    "unemployment_rate": {"index": 1, "gold": 1,
                          "hot": "vyšší nezaměstnanost → holubičí",
                          "cool": "nižší nezaměstnanost → jestřábí"},
    "growth": {"index": 1, "gold": 0,
               "hot": "silnější růst → risk-on",
               "cool": "slabší růst → risk-off"},
    "survey": {"index": 1, "gold": 0,
               "hot": "lepší sentiment / aktivita → risk-on",
               "cool": "horší sentiment / aktivita → risk-off"},
}


def classify_event(title: str) -> str | None:
    """Zařadí event podle titulku do makro kategorie (None = neznámý typ)."""
    t = (title or "").lower()
    if "unemployment claims" in t or "jobless" in t:
        return "claims"
    if "unemployment rate" in t:
        return "unemployment_rate"
    if any(k in t for k in ("cpi", "ppi", "pce", "inflation", "price index")):
        return "inflation"
    if any(k in t for k in ("average hourly earnings", "average earnings", "wage")):
        return "wages"
    if any(k in t for k in ("non-farm", "nonfarm", "payroll", "employment change", "adp", "nfp")):
        return "jobs"
    if any(k in t for k in ("gdp", "retail sales", "durable goods", "industrial production")):
        return "growth"
    if any(k in t for k in ("ism", "pmi", "manufacturing", "services", "confidence", "sentiment")):
        return "survey"
    if any(k in t for k in ("fomc", "federal funds", "interest rate", "rate statement", "powell", "fed chair")):
        return "rates"
    return None


def _dir_word(sign: float) -> str:
    return "nahoru" if sign > 0 else "dolů" if sign < 0 else "spíš neutrálně"


def _intensity(sens: float, is_gold: bool) -> str:
    if is_gold:
        return "výrazně" if abs(sens) >= 1 else "mírně"
    return "silně" if sens >= 0.9 else "středně" if sens >= 0.75 else "mírně"


def scenario_for(category: str, ticker: str) -> dict | None:
    """Vrátí scénáře {hot, inline, cool} pro daný instrument a kategorii eventu.
    Každý scénář = {dir: 'up'|'down'|'flat', text}."""
    cat = _CATEGORIES.get(category)
    if cat is None:
        return None
    is_gold = ticker.upper() in GOLD_SYMBOLS
    base = cat["gold" if is_gold else "index"]
    sens = 1.0 if is_gold else INDEX_SENSITIVITY.get(ticker.upper(), 0.7)
    tech_note = " (tech nejcitlivější na sazby)" if ticker.upper() == "NQ" and not is_gold else ""

    def leg(sign_mult: int, reason_key: str) -> dict:
        sign = base * sign_mult
        d = "up" if sign > 0 else "down" if sign < 0 else "flat"
        if sign == 0:
            return {"dir": "flat", "text": "malý čistý dopad"}
        return {"dir": d, "text": f"{cat[reason_key]} → {_intensity(sens, is_gold)} {_dir_word(sign)}{tech_note}"}

    return {
        "hot": leg(1, "hot"),      # výsledek NAD forecastem
        "cool": leg(-1, "cool"),   # výsledek POD forecastem
        "inline": {"dir": "flat", "text": "výsledek dle očekávání → malý pohyb, trh to má v ceně"},
    }


def _today_events(events: list[dict], today_iso: str) -> list[dict]:
    """Jen dnešní eventy (dle UTC data v time_utc), high první."""
    todays = [e for e in events if (e.get("time_utc") or "")[:10] == today_iso]
    todays.sort(key=lambda e: (0 if e.get("impact") == "high" else 1, e.get("time_utc") or ""))
    return todays


async def build_outlook(ticker_symbol: str) -> dict:
    """Sestaví deterministickou část výhledu (eventy + scénáře) pro instrument."""
    now = datetime.now(timezone.utc)
    today_iso = now.date().isoformat()
    # Široké okno: ~13h zpět (ranní eventy) + ~15h vpřed, pak filtr na dnešní datum.
    raw = await get_upcoming_events(window_before_min=900, window_after_min=780)
    events = _today_events(raw, today_iso)

    scenarios = []
    for e in events:
        if e.get("impact") not in ("high", "medium"):
            continue
        cat = classify_event(e.get("title", ""))
        if cat is None:
            continue
        sc = scenario_for(cat, ticker_symbol)
        if sc is None:
            continue
        # Pokud už je actual, urči který scénář nastal (vs forecast).
        realized = _realized_bucket(e.get("actual"), e.get("forecast"))
        scenarios.append({
            "title": e.get("title"), "time_utc": e.get("time_utc"), "impact": e.get("impact"),
            "forecast": e.get("forecast"), "previous": e.get("previous"), "actual": e.get("actual"),
            "category": cat, "realized": realized, **sc,
        })
    return {"ticker": ticker_symbol, "date": today_iso, "events": events, "scenarios": scenarios}


def _num(v) -> float | None:
    """Vytáhne číslo z '0.3%', '202K', '-0.3%' apod."""
    if not v:
        return None
    s = str(v).strip().replace("%", "").replace(",", "")
    mult = 1.0
    if s.endswith("K"):
        mult, s = 1e3, s[:-1]
    elif s.endswith("M"):
        mult, s = 1e6, s[:-1]
    elif s.endswith("B"):
        mult, s = 1e9, s[:-1]
    try:
        return float(s) * mult
    except ValueError:
        return None


def _realized_bucket(actual, forecast) -> str | None:
    """'hot' | 'inline' | 'cool' | None — porovná actual vs forecast."""
    a, f = _num(actual), _num(forecast)
    if a is None or f is None:
        return None
    # Tolerance pro 'inline': ±5 % rozdílu vůči forecastu (min. malý absolutní práh).
    tol = max(abs(f) * 0.05, 0.05)
    if a > f + tol:
        return "hot"
    if a < f - tol:
        return "cool"
    return "inline"


def _parse_event_values(body: str, title: str) -> tuple[str | None, str | None]:
    """Vytáhne (forecast, actual) z body eventu ('Forecast: X', 'Actual: Y') nebo titulku."""
    import re
    src = f"{body or ''}\n{title or ''}"
    fc = re.search(r"Forecast:\s*([^\n|]+)", src)
    ac = re.search(r"Actual:\s*([^\n|]+)", src)
    f = fc.group(1).strip() if fc else None
    a = ac.group(1).strip() if ac else None
    return (f if f and f not in ("?", "N/A") else None,
            a if a and a not in ("?", "N/A") else None)


async def compute_scenario_stats(session, ticker_symbol: str, days: int = 90) -> dict:
    """Úspěšnost scénářů: pro minulé vydané eventy porovná predikovaný směr (dle
    scénáře pro nastalý bucket hot/cool) se SKUTEČNÝM pohybem ceny 1h po eventu
    (MarketReaction.pct_change_1h). Deterministické → počítá se z existujících dat."""
    from datetime import datetime, timedelta
    from sqlalchemy import select
    from app.models import NewsItem, MarketReaction, Ticker

    ticker = await session.scalar(select(Ticker).where(Ticker.symbol == ticker_symbol.upper()))
    if not ticker:
        return {"ticker": ticker_symbol, "days": days, "overall": {"n": 0, "hits": 0, "hit_rate": None},
                "by_category": {}}
    since = datetime.utcnow() - timedelta(days=days)

    # Skutečný směr = realized_direction (kalibrace, primární ~30min okno; jednotkově
    # bezpečné). Fallback na znaménko pct_change_1h/15m proti neutral_threshold.
    thr = ticker.neutral_threshold
    rows = (await session.execute(
        select(NewsItem.title, NewsItem.body, MarketReaction.realized_direction,
               MarketReaction.pct_change_1h, MarketReaction.pct_change_15m)
        .join(MarketReaction, (MarketReaction.news_id == NewsItem.id) & (MarketReaction.ticker_id == ticker.id))
        .where(NewsItem.published_at >= since)
        .where(NewsItem.title.like("%Actual:%"))
    )).all()

    def _actual_dir(rdir, pct1h, pct15) -> str | None:
        if rdir is not None:
            v = rdir.value if hasattr(rdir, "value") else str(rdir)
            return "flat" if v == "neutral" else v
        pct = pct1h if pct1h is not None else pct15
        if pct is None:
            return None
        return "up" if pct > thr else "down" if pct < -thr else "flat"

    by_cat: dict[str, dict] = {}
    overall = {"n": 0, "hits": 0}
    for title, body, rdir, pct1h, pct15 in rows:
        actual_dir = _actual_dir(rdir, pct1h, pct15)
        if actual_dir is None:
            continue
        cat = classify_event(title)
        if cat is None:
            continue
        fc, act = _parse_event_values(body, title)
        bucket = _realized_bucket(act, fc)
        if bucket not in ("hot", "cool"):   # jen směrové scénáře (inline nehodnotíme)
            continue
        sc = scenario_for(cat, ticker_symbol)
        if sc is None:
            continue
        pred_dir = sc[bucket]["dir"]
        if pred_dir not in ("up", "down"):
            continue
        hit = pred_dir == actual_dir
        c = by_cat.setdefault(cat, {"n": 0, "hits": 0})
        c["n"] += 1
        c["hits"] += 1 if hit else 0
        overall["n"] += 1
        overall["hits"] += 1 if hit else 0

    def _rate(d: dict) -> float | None:
        return round(100 * d["hits"] / d["n"], 1) if d["n"] else None

    return {
        "ticker": ticker_symbol, "days": days,
        "overall": {**overall, "hit_rate": _rate(overall)},
        "by_category": {k: {**v, "hit_rate": _rate(v)} for k, v in by_cat.items()},
    }
