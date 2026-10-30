"""Výsledky hospodaření firem: AI vytěžení tiskové zprávy (SEC 8-K, EX-99.1) + české vysvětlení.

LLM dostane text tiskové zprávy a konsenzus EPS. Čísla smí brát JEN z dodaného textu (nic
nedopočítávat), verdikt = jak zprávu hodnotit fundamentálně (pozitivní / negativní / smíšené).
Druhá fáze (po ~45 min) dostane reakci ceny + titulky zpráv a vysvětlí, proč trh reaguje tak, jak reaguje.
Není to investiční doporučení — prompt výslovně zakazuje doporučovat nákup/prodej.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.valuation.models import ValEarningsReport, ValInstrument

log = structlog.get_logger(__name__)

VERDICTS = ("positive", "negative", "mixed", "neutral")
MAX_PRESS_CHARS = 45_000
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

EXTRACT_SYSTEM = (
    "Jsi finanční analytik. Dostaneš text tiskové zprávy o výsledcích hospodaření americké firmy "
    "(SEC 8-K, exhibit 99.1) a konsenzus odhadu EPS analytiků. Vrať POUZE validní JSON (bez markdownu):\n"
    "{\n"
    '  "fiscal_period": string|null,      // např. "Q3 2026"\n'
    '  "revenue_usd": number|null,        // celkové tržby za čtvrtletí v USD (např. 102300000000)\n'
    '  "revenue_yoy_pct": number|null,    // meziroční růst tržeb v %, jen pokud je v textu nebo jde přímo odečíst\n'
    '  "eps_diluted": number|null,        // zředěný EPS za čtvrtletí (GAAP, pokud firma uvádí jen non-GAAP, ten)\n'
    '  "verdict": "positive"|"negative"|"mixed"|"neutral",\n'
    '  "headline_cs": string,             // 1 věta česky: co je hlavní zpráva\n'
    '  "summary_cs": string,              // 3–5 odrážek česky (každá začíná "- "), co se stalo a co to znamená pro firmu\n'
    '  "guidance_cs": string|null         // výhled vedení na další období, pokud ho zpráva obsahuje\n'
    "}\n"
    "Pravidla: čísla ber VÝHRADNĚ z dodaného textu, nic nedopočítávej ani neodhaduj — co v textu není, dej null. "
    "Verdikt hodnotí zprávu fundamentálně (růst, marže, zisk vs. konsenzus, výhled, jednorázové vlivy). "
    "Když jsou dobré tržby, ale zisk pod odhadem (nebo naopak), je to 'mixed'. "
    "Vysvětluj srozumitelně pro retailového tradera, česky, bez anglických zkratek kde to jde. "
    "NIKDY nedoporučuj nákup ani prodej akcie."
)

REACTION_SYSTEM = (
    "Jsi finanční analytik. Dostaneš shrnutí výsledků hospodaření firmy, reakci ceny akcie po zveřejnění "
    "a titulky zpráv, které po zveřejnění vyšly. Napiš česky 2–4 krátké odrážky (každá začíná \"- \"), "
    "PROČ trh reaguje tak, jak reaguje (co investoři nejspíš řeší: zisk vs. odhad, výhled, výdaje, "
    "konkrétní segment…). Opírej se jen o dodané informace; když z nich důvod nejde poznat, řekni to. "
    "NIKDY nedoporučuj nákup ani prodej. Odpověz jen odrážkami."
)


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


def _llm_json(system: str, user: str, max_tokens: int = 1400) -> tuple[dict | None, str | None]:
    from app.llm.client import llm_client
    try:
        msg = llm_client._get_client().messages.create(
            model=settings.claude_model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}])
        text = msg.content[0].text.strip()
        m = re.search(r"\{.*\}", text, flags=re.S)
        return (json.loads(m.group(0)) if m else None), settings.claude_model
    except Exception as e:  # noqa: BLE001
        log.warning("Earnings LLM failed", error=str(e)[:300])
        return None, None


def _llm_text(system: str, user: str, max_tokens: int = 600) -> str | None:
    from app.llm.client import llm_client
    try:
        msg = llm_client._get_client().messages.create(
            model=settings.claude_model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}])
        return msg.content[0].text.strip()[:2000]
    except Exception as e:  # noqa: BLE001
        log.warning("Earnings reaction LLM failed", error=str(e)[:300])
        return None


def _bullets(v) -> str:
    if isinstance(v, list):
        return "\n".join(f"- {str(x).lstrip('- ').strip()}" for x in v if x)
    return str(v or "").strip()


def _num(v) -> float | None:
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def analyze_press_release(ticker: str, name: str | None, press_text: str,
                          eps_estimate: float | None, n_estimates: int | None) -> dict:
    """Vytěží čísla a napíše vysvětlení. Při selhání LLM vrátí prázdný dict (záznam se uloží i tak)."""
    cons = (f"Konsenzus EPS analytiků: {eps_estimate} (počet odhadů: {n_estimates})"
            if eps_estimate is not None else "Konsenzus EPS: není k dispozici")
    user = (f"Firma: {name or ticker} ({ticker})\n{cons}\n\nTisková zpráva:\n"
            f"{press_text[:MAX_PRESS_CHARS]}")
    data, model = _llm_json(EXTRACT_SYSTEM, user)
    if not data:
        return {}
    verdict = data.get("verdict") if data.get("verdict") in VERDICTS else None
    return {
        "fiscal_period": (data.get("fiscal_period") or None) and str(data["fiscal_period"])[:40],
        "revenue": _num(data.get("revenue_usd")),
        "revenue_yoy_pct": _num(data.get("revenue_yoy_pct")),
        "eps_llm": _num(data.get("eps_diluted")),
        "verdict": verdict,
        "headline_cs": (data.get("headline_cs") or "")[:300] or None,
        "summary_cs": _bullets(data.get("summary_cs"))[:4000] or None,
        "guidance_cs": (data.get("guidance_cs") or None) and str(data["guidance_cs"])[:1000],
        "llm_model": model,
    }


def explain_reaction(r: ValEarningsReport, name: str | None) -> str | None:
    news = "\n".join(f"- {n['title']}" for n in (r.related_news or [])) or "(žádné titulky)"
    eps = (f"EPS {r.eps_actual} vs. konsenzus {r.eps_estimate}" if r.eps_actual is not None and r.eps_estimate is not None
           else "EPS vs. konsenzus: neznámé")
    user = (f"Firma: {name or r.ticker} ({r.ticker})\nObdobí: {r.fiscal_period or '?'}\n"
            f"Shrnutí výsledků:\n{r.headline_cs or ''}\n{r.summary_cs or ''}\n{eps}\n"
            f"Výhled: {r.guidance_cs or 'neuveden'}\n"
            f"Reakce ceny od zveřejnění: {r.reaction_pct:+.2f} %\n\nTitulky po zveřejnění:\n{news}")
    return _llm_text(REACTION_SYSTEM, user)


def report_out(r: ValEarningsReport, name: str | None = None) -> dict:
    return {
        "id": r.id, "ticker": r.ticker, "name": name, "accepted_at": r.accepted_at.isoformat() + "Z",
        "source_url": r.source_url, "fiscal_period": r.fiscal_period,
        "revenue": r.revenue, "revenue_yoy_pct": r.revenue_yoy_pct,
        "eps_actual": r.eps_actual, "eps_estimate": r.eps_estimate, "eps_surprise_pct": r.eps_surprise_pct,
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
