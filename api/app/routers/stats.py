from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.repositories import NewsRepository, TickerRepository

router = APIRouter(prefix="/api/stats", tags=["stats"])


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
