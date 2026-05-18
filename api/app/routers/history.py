from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import NewsPrediction, MarketReaction, NewsItem
from app.repositories import TickerRepository
from app.schemas import HistoryPoint

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("", response_model=list[HistoryPoint])
async def get_history(
    ticker: str = Query(default="EURUSD"),
    days: int = Query(default=90, le=365),
    session: AsyncSession = Depends(get_session),
):
    ticker_repo = TickerRepository(session)
    ticker_obj = await ticker_repo.get_by_symbol(ticker)
    if not ticker_obj:
        return []

    from datetime import timedelta
    cutoff = date.today() - timedelta(days=days)

    stmt = (
        select(
            func.date(NewsItem.published_at).label("pub_date"),
            MarketReaction.realized_direction,
            NewsPrediction.prob_down,
            NewsPrediction.prob_neutral,
            NewsPrediction.prob_up,
        )
        .join(NewsPrediction, NewsPrediction.news_id == MarketReaction.news_id)
        .join(NewsItem, NewsItem.id == MarketReaction.news_id)
        .where(
            MarketReaction.ticker_id == ticker_obj.id,
            NewsPrediction.ticker_id == ticker_obj.id,
            MarketReaction.realized_direction.isnot(None),
            func.date(NewsItem.published_at) >= cutoff,
        )
        .order_by(func.date(NewsItem.published_at).desc())
        .limit(500)
    )
    result = await session.execute(stmt)
    rows = result.all()

    points = []
    for row in rows:
        best = max(
            [("down", row.prob_down), ("neutral", row.prob_neutral), ("up", row.prob_up)],
            key=lambda x: x[1],
        )
        predicted = best[0]
        realized = row.realized_direction if isinstance(row.realized_direction, str) else row.realized_direction.value

        points.append(HistoryPoint(
            date=row.pub_date,
            realized_direction=realized,
            predicted_direction=predicted,
            prob_down=row.prob_down,
            prob_neutral=row.prob_neutral,
            prob_up=row.prob_up,
            accuracy=predicted == realized,
        ))

    return points
