"""Výsledky hospodaření firem: uložení analýzy tiskové zprávy (SEC 8-K, EX-99.1) + české vysvětlení.

Texty píše lokální model na Sparku (gpt-oss přes LiteLLM ve scripts/spark/earnings_watch.py, tam jsou
i prompty) — backend žádný LLM nevolá, jen normalizuje a ukládá. Druhá fáze (po ~45 min) dostane
reakci ceny + titulky zpráv a vysvětlí, proč trh reaguje tak, jak reaguje.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.valuation.models import ValEarningsReport, ValInstrument

VERDICTS = ("positive", "negative", "mixed", "neutral")
REACTION_ANALYSIS_AFTER = timedelta(minutes=45)

# Jak se firma jmenuje v titulcích (kde první slovo názvu nestačí / je obecné).
NAME_ALIASES = {
    "GOOGL": ["Alphabet", "Google"], "GOOG": ["Alphabet", "Google"], "META": ["Meta", "Facebook"],
    "LLY": ["Eli Lilly", "Lilly"], "JNJ": ["Johnson & Johnson", "J&J"], "AMD": ["AMD"],
    "MCD": ["McDonald"], "COST": ["Costco"], "MRK": ["Merck"], "NKE": ["Nike"], "PLTR": ["Palantir"],
    "VRTX": ["Vertex"], "AVGO": ["Broadcom"], "NFLX": ["Netflix"], "MSFT": ["Microsoft"],
    "AMZN": ["Amazon"], "AAPL": ["Apple"], "NVDA": ["Nvidia"], "TSLA": ["Tesla"],
}
_GENERIC = {"the", "inc", "corp", "group", "holdings", "company", "international", "global", "first", "american"}

def aliases(ticker: str, name: str | None) -> list[str]:
    out = list(NAME_ALIASES.get(ticker.upper(), []))
    first = re.sub(r"[^A-Za-z&]", "", (name or "").split(" ")[0]) if name else ""
    if len(first) >= 4 and first.lower() not in _GENERIC and not out:
        out.append(first.capitalize() if first.isupper() else first)
    return out + [ticker.upper()]


def _matches(title: str, names: list[str]) -> bool:
    for n in names:
        # ticker jen jako samostatné slovo velkými písmeny (ať „META“ nechytá „metal“)
        pat = rf"\b{re.escape(n)}\b" if not n.isupper() else rf"(?<![A-Za-z]){re.escape(n)}(?![a-z])"
        if re.search(pat, title, flags=0 if n.isupper() else re.IGNORECASE):
            return True
    return False


async def related_news(session: AsyncSession, ticker: str, name: str | None,
                       start: datetime, end: datetime, limit: int = 12) -> list[dict]:
    """Titulky z našich zdrojů o firmě v okně [start, end]."""
    from app.models import NewsItem, NewsSource
    rows = (await session.execute(
        select(NewsItem.title, NewsItem.url, NewsItem.published_at, NewsSource.name)
        .join(NewsSource, NewsSource.id == NewsItem.source_id)
        .where(NewsItem.published_at >= start, NewsItem.published_at <= end)
        .order_by(NewsItem.published_at))).all()
    names = aliases(ticker, name)
    out = []
    for title, url, pub, src in rows:
        if title and _matches(title, names):
            out.append({"title": title[:300], "url": url, "source": src.replace("rss_", ""),
                        "published_at": pub.isoformat() if pub else None})
    return out[-limit:]


def _bullets(v) -> str:
    if isinstance(v, list):
        return "\n".join(f"- {str(x).lstrip('- ').strip()}" for x in v if x)
    return str(v or "").strip()


def _num(v) -> float | None:
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def normalize_analysis(data: dict | None, model: str | None) -> dict:
    """Výstup LLM ze Sparku (JSON dle EXTRACT promptu ve workeru) → pole reportu. Prázdný dict = bez analýzy."""
    if not isinstance(data, dict) or not data:
        return {}
    verdict = data.get("verdict") if data.get("verdict") in VERDICTS else None
    return {
        "fiscal_period": (data.get("fiscal_period") or None) and str(data["fiscal_period"])[:40],
        "revenue": _num(data.get("revenue_usd")),
        "revenue_yoy_pct": _num(data.get("revenue_yoy_pct")),
        "eps_gaap": _num(data.get("eps_gaap")),
        "eps_adjusted": _num(data.get("eps_adjusted")),
        "verdict": verdict,
        "headline_cs": str(data.get("headline_cs") or "")[:300] or None,
        "summary_cs": _bullets(data.get("summary_cs"))[:4000] or None,
        "guidance_cs": (data.get("guidance_cs") or None) and str(data["guidance_cs"])[:1000],
        "llm_model": (model or "")[:60] or None,
    }


def reaction_context(r: ValEarningsReport, name: str | None) -> dict:
    """Podklady, ze kterých Spark napíše „proč trh reaguje“."""
    return {"name": name or r.ticker, "ticker": r.ticker, "fiscal_period": r.fiscal_period,
            "headline_cs": r.headline_cs, "summary_cs": r.summary_cs, "guidance_cs": r.guidance_cs,
            "eps_actual": r.eps_actual, "eps_estimate": r.eps_estimate, "reaction_pct": r.reaction_pct,
            "news": [n["title"] for n in (r.related_news or [])]}


def report_out(r: ValEarningsReport, name: str | None = None) -> dict:
    return {
        "id": r.id, "ticker": r.ticker, "name": name, "accepted_at": r.accepted_at.isoformat() + "Z",
        "source_url": r.source_url, "fiscal_period": r.fiscal_period,
        "revenue": r.revenue, "revenue_yoy_pct": r.revenue_yoy_pct,
        "eps_actual": r.eps_actual, "eps_gaap": r.eps_gaap, "eps_estimate": r.eps_estimate, "eps_surprise_pct": r.eps_surprise_pct,
        "n_estimates": r.n_estimates, "verdict": r.verdict, "headline_cs": r.headline_cs,
        "summary_cs": r.summary_cs, "guidance_cs": r.guidance_cs,
        "price_before": r.price_before, "price_now": r.price_now, "reaction_pct": r.reaction_pct,
        "reaction_at": r.reaction_at.isoformat() + "Z" if r.reaction_at else None,
        "reaction_cs": r.reaction_cs, "related_news": r.related_news or [],
    }


async def instrument_names(session: AsyncSession, tickers: list[str]) -> dict[str, str | None]:
    if not tickers:
        return {}
    rows = (await session.execute(select(ValInstrument.ticker, ValInstrument.name)
                                  .where(ValInstrument.ticker.in_(tickers)))).all()
    return dict(rows)
