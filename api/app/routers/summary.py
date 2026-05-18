from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.repositories import NewsRepository, TickerRepository
from app.schemas import DailySummaryOut

router = APIRouter(prefix="/api/summary", tags=["summary"])


@router.get("/daily", response_model=DailySummaryOut)
async def get_daily_summary(
    ticker: str = Query(default="EURUSD"),
    date_filter: date | None = Query(default=None, alias="date"),
    session: AsyncSession = Depends(get_session),
):
    ticker_repo = TickerRepository(session)
    ticker_obj = await ticker_repo.get_by_symbol(ticker)
    if not ticker_obj:
        raise HTTPException(status_code=404, detail=f"Ticker {ticker} nenalezen")

    for_date = date_filter or date.today()
    news_repo = NewsRepository(session)
    summary = await news_repo.get_daily_summary(ticker_obj.id, for_date)
    if not summary:
        raise HTTPException(status_code=404, detail="Summary pro tento den neexistuje")
    return summary
