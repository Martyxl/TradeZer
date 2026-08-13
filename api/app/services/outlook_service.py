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


EVAL_TICKERS = ["NQ", "ES", "YM", "XAUUSD"]


async def compute_scenario_stats(session, ticker_symbol: str, days: int = 90) -> dict:
    """Úspěšnost scénářů z tabulky OutlookEval (plní denní eval job): kolik % případů
    predikovaný směr scénáře seděl se skutečným ~1h pohybem ceny. Per kategorie."""
    from datetime import date as _date, timedelta
    from sqlalchemy import select
    from app.models import Ticker, OutlookEval

    ticker = await session.scalar(select(Ticker).where(Ticker.symbol == ticker_symbol.upper()))
    if not ticker:
        return {"ticker": ticker_symbol, "days": days,
                "overall": {"n": 0, "hits": 0, "hit_rate": None}, "by_category": {}}
    since = _date.today() - timedelta(days=days)
    rows = (await session.execute(
        select(OutlookEval).where(
            OutlookEval.ticker_id == ticker.id,
            OutlookEval.eval_date >= since,
            OutlookEval.hit.isnot(None),
        )
    )).scalars().all()

    by_cat: dict[str, dict] = {}
    overall = {"n": 0, "hits": 0}
    for r in rows:
        c = by_cat.setdefault(r.category, {"n": 0, "hits": 0})
        c["n"] += 1
        c["hits"] += 1 if r.hit else 0
        overall["n"] += 1
        overall["hits"] += 1 if r.hit else 0

    def _rate(d: dict) -> float | None:
        return round(100 * d["hits"] / d["n"], 1) if d["n"] else None

    return {
        "ticker": ticker_symbol, "days": days,
        "overall": {**overall, "hit_rate": _rate(overall)},
        "by_category": {k: {**v, "hit_rate": _rate(v)} for k, v in by_cat.items()},
    }


async def evaluate_outlook(session) -> dict:
    """Denní eval job: pro dnešní vydané eventy (s actual) spočítá pro každý instrument
    nastalý scénář + skutečný ~1h pohyb ceny (Yahoo) + zda predikce seděla; uloží do
    OutlookEval (idempotentně). Event zpracuje až ≥70 min po vydání (kvůli 1h ceně)."""
    import asyncio
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select
    from app.models import Ticker, OutlookEval
    from app.sources.yahoo_finance_adapter import YahooFinanceAdapter, _find_close_at

    now = datetime.now(timezone.utc)
    raw = await get_upcoming_events(window_before_min=60, window_after_min=1440)  # posledních ~24h
    tickers = (await session.execute(
        select(Ticker).where(Ticker.symbol.in_(EVAL_TICKERS))
    )).scalars().all()
    yahoo = YahooFinanceAdapter()
    created = 0

    for e in raw:
        if e.get("impact") not in ("high", "medium"):
            continue
        cat = classify_event(e.get("title", ""))
        if cat is None:
            continue
        actual = (e.get("actual") or "").strip()
        if not actual:                       # ještě není výsledek
            continue
        try:
            ev_dt = datetime.fromisoformat((e.get("time_utc") or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if (now - ev_dt).total_seconds() < 70 * 60:   # počkej na 1h cenových dat
            continue
        bucket = _realized_bucket(actual, e.get("forecast"))
        eval_date = ev_dt.date()
        title = (e.get("title") or "")[:200]

        for t in tickers:
            exists = await session.scalar(select(OutlookEval).where(
                OutlookEval.eval_date == eval_date, OutlookEval.ticker_id == t.id,
                OutlookEval.event_title == title))
            if exists:
                continue
            sc = scenario_for(cat, t.symbol)
            pred = sc[bucket]["dir"] if (sc and bucket in ("hot", "cool", "inline")) else None
            move = adir = None
            try:
                bars = await asyncio.to_thread(yahoo.fetch_day_bars, t.symbol, eval_date)
                p0 = _find_close_at(bars, ev_dt, 15)
                p1 = _find_close_at(bars, ev_dt + timedelta(minutes=60), 15)
                if p0 and p1:
                    move = (p1 - p0) / p0
                    thr = t.neutral_threshold
                    adir = "up" if move > thr else "down" if move < -thr else "flat"
            except Exception:  # noqa: BLE001
                pass
            hit = None
            if bucket in ("hot", "cool") and pred in ("up", "down") and adir is not None:
                hit = (pred == adir)
            session.add(OutlookEval(
                eval_date=eval_date, ticker_id=t.id, event_title=title, category=cat,
                forecast=e.get("forecast"), actual=actual, realized_bucket=bucket,
                predicted_dir=pred, actual_dir=adir, hit=hit,
                price_move_pct=round(move * 100, 4) if move is not None else None,
                event_time_utc=ev_dt.replace(tzinfo=None)))
            created += 1

    if created:
        await session.commit()
    return {"created": created, "tickers": [t.symbol for t in tickers]}
