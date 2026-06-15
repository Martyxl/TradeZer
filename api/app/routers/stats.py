from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.repositories import NewsRepository, TickerRepository

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/calendar/active")
async def calendar_active(
    window_before_min: int = Query(default=90, description="Minuty před eventem = začátek aktivního okna"),
    window_after_min: int = Query(default=30, description="Minuty po eventu = konec aktivního okna"),
):
    """Zjistí jestli je trh v aktivním okně ekonomického eventu (USD/EUR/CNY, high/medium).

    Vrátí active=true pokud je libovolný event v okně [now-after, now+before].
    Používá se v GitHub Actions cron pro smart scheduling LLM predikcí —
    predikce se spouštějí jen když je blízko relevantní ekonomický event.
    """
    from app.sources.forex_factory import get_upcoming_events

    events = await get_upcoming_events(
        window_before_min=window_before_min,
        window_after_min=window_after_min,
    )
    active = len(events) > 0
    next_event = events[0] if events else None

    return {
        "active": active,
        "window_before_min": window_before_min,
        "window_after_min": window_after_min,
        "events_in_window": len(events),
        "next_event": next_event,
        "upcoming": events,
    }


@router.get("")
async def get_stats(
    ticker: str = Query(default="EURUSD"),
    days: int = Query(default=90, le=365),
    session: AsyncSession = Depends(get_session),
):
    """Agregované statistiky přesnosti predikcí — celkem + per kategorie."""
    ticker_repo = TickerRepository(session)
    ticker_obj = await ticker_repo.get_by_symbol(ticker)
    if not ticker_obj:
        return {"error": "ticker not found"}

    repo = NewsRepository(session)
    stats = await repo.get_accuracy_stats(ticker_obj.id, days=days)
    return {
        "ticker": ticker,
        "days": days,
        **stats,
    }


@router.get("/patterns")
async def get_patterns(
    ticker: str = Query(default="EURUSD"),
    days: int = Query(default=180, le=365),
    category: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    """Historické vzory pohybu trhu po zprávách — pattern memory pro daný ticker.

    Vrátí per-kategorie statistiky:
    - typický pohyb (avg, p75) za 30 minut
    - liquidity_grab_rate: jak často trh nejdříve jde falešným směrem
    - dominant_direction: nejčastější výsledek (up/down/neutral)
    Použití: příprava na nadcházející zprávu (PMI, FOMC, CPI...).
    """
    ticker_repo = TickerRepository(session)
    ticker_obj = await ticker_repo.get_by_symbol(ticker.upper())
    if not ticker_obj:
        return {"error": "ticker not found", "ticker": ticker}

    repo = NewsRepository(session)

    ALL_CATEGORIES = [
        "monetary_policy", "inflation", "employment", "gdp", "pmi",
        "fed_speech", "ecb_speech", "geopolitical", "trade_balance",
        "central_bank_minutes", "retail_sales", "housing", "consumer_confidence",
        "energy", "earnings", "risk_sentiment", "fiscal_policy",
        "surprise_beat", "surprise_miss", "safe_haven", "equity_index", "tech_sector",
    ]
    categories = [category] if category else ALL_CATEGORIES

    patterns = await repo.get_category_patterns(
        ticker_obj.id, categories, days=days, min_samples=3
    )

    return {
        "ticker": ticker.upper(),
        "days": days,
        "pattern_count": len(patterns),
        "patterns": patterns,
    }
