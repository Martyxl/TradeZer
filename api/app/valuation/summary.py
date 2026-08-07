"""LLM shrnutí valuace — jen NAD spočítanými čísly, cache 24 h dle hashe vstupu.

LLM nikdy nepočítá ani nedopočítává. Dostane strukturovaný JSON hotových čísel a
napíše 3 české odrážky. Když LLM selže → prázdné shrnutí; modul na LLM nezávisí.
Konfigurace přes .env (LLM_BASE_URL/LLM_MODEL/LLM_API_KEY) — funguje proti
OpenAI-compatible (LiteLLM/lokál) i Anthropic bez změny kódu.
"""
from __future__ import annotations

import hashlib
import json

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.valuation.models import ValSummary, ValScoreDaily, ValMetricsDaily, ValInstrument

log = structlog.get_logger(__name__)

SYSTEM_PROMPT = (
    "Jsi finanční analytik. Dostaneš JSON s HOTOVÝMI spočítanými čísly o akcii. "
    "Napiš stručné shrnutí česky ve 3 odrážkách, každá max 40 slov. "
    "Používej VÝHRADNĚ dodaná čísla — nic nedopočítávej ani neodhaduj. "
    "Pokud údaj chybí (null), napiš že chybí. NIKDY nedoporučuj nákup ani prodej. "
    "Odpověz jen 3 odrážkami začínajícími '- ', bez úvodu a závěru."
)


def _payload(inst, score, metrics: dict) -> dict:
    return {
        "ticker": score.ticker,
        "nazev": inst.name if inst else None,
        "skupina": inst.group_key if inst else None,
        "verdikt_valuace": score.valuation_verdict,
        "verdikt_horizont": score.horizon_verdict,
        "bublina": score.bubble_flag,
        "confidence": score.confidence,
        "skore": {
            "valuace": score.valuation_score, "rust": score.growth_score,
            "kvalita": score.quality_score, "revize": score.revision_score,
            "trend": score.trend_score, "composite": score.composite_score,
        },
        "metriky": {
            "pe_fwd": metrics.get("pe_fwd"), "pctile_pe_fwd": metrics.get("pctile_pe_fwd"),
            "eps_growth_ntm": metrics.get("eps_growth_ntm"),
            "revenue_growth_ntm": metrics.get("revenue_growth_ntm"),
            "roic": metrics.get("roic"), "fcf_margin": metrics.get("fcf_margin"),
            "net_debt_to_ebitda": metrics.get("net_debt_to_ebitda"),
            "revision_ratio_30d": metrics.get("revision_ratio_30d"),
        },
    }


def _hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _call_llm(payload: dict) -> str | None:
    """OpenAI-compatible (pokud LLM_BASE_URL), jinak Anthropic. Chyba → None."""
    user = json.dumps(payload, ensure_ascii=False)
    try:
        if settings.llm_base_url:
            import httpx
            resp = httpx.post(
                f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.llm_api_key or 'local'}",
                         "Content-Type": "application/json"},
                json={"model": settings.llm_model or "gpt-4o-mini", "temperature": 0.2,
                      "max_tokens": 300,
                      "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                                   {"role": "user", "content": user}]},
                timeout=40.0)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        if settings.anthropic_api_key:
            import anthropic
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            msg = client.messages.create(
                model=settings.claude_classifier_model, max_tokens=300, temperature=0.2,
                system=SYSTEM_PROMPT, messages=[{"role": "user", "content": user}])
            return msg.content[0].text.strip()
    except Exception as e:  # noqa: BLE001
        log.warning("Valuation summary LLM failed", ticker=payload.get("ticker"), error=str(e))
    return None


async def get_summary(session: AsyncSession, ticker: str) -> dict:
    ticker = ticker.upper()
    version = settings.val_model_version
    score = await session.scalar(select(ValScoreDaily).where(
        ValScoreDaily.ticker == ticker, ValScoreDaily.model_version == version)
        .order_by(ValScoreDaily.as_of_date.desc()).limit(1))
    if score is None:
        return {"ticker": ticker, "summary": "", "cached": False}

    mrow = await session.scalar(select(ValMetricsDaily).where(
        ValMetricsDaily.ticker == ticker, ValMetricsDaily.as_of_date == score.as_of_date,
        ValMetricsDaily.model_version == version))
    inst = await session.scalar(select(ValInstrument).where(ValInstrument.ticker == ticker))

    payload = _payload(inst, score, mrow.metrics if mrow else {})
    h = _hash(payload)

    cached = await session.scalar(select(ValSummary).where(
        ValSummary.ticker == ticker, ValSummary.input_hash == h))
    if cached:
        return {"ticker": ticker, "summary": cached.summary, "cached": True, "llm_model": cached.llm_model}

    text = _call_llm(payload)
    if not text:
        return {"ticker": ticker, "summary": "", "cached": False}  # modul nezávisí na LLM

    llm_model = settings.llm_model or settings.claude_classifier_model
    session.add(ValSummary(ticker=ticker, input_hash=h, summary=text[:2000], llm_model=llm_model))
    await session.commit()
    return {"ticker": ticker, "summary": text, "cached": False, "llm_model": llm_model}
