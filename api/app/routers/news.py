from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.repositories import NewsRepository, TickerRepository
from app.schemas import NewsItemOut, NewsItemDetail, RefreshResponse, TickerImpactOut
from app.services.news_aggregator import NewsAggregator


class CalendarEventOut(BaseModel):
    id: int
    title: str
    published_at: datetime
    categories: list[str]
    max_weight: float

router = APIRouter(prefix="/api/news", tags=["news"])


@router.get("", response_model=list[NewsItemOut])
async def list_news(
    ticker: str = Query(default="EURUSD"),
    date_filter: date | None = Query(default=None, alias="date"),
    limit: int = Query(default=settings.feed_page_size, le=100),
    offset: int = Query(default=0),
    session: AsyncSession = Depends(get_session),
):
    ticker_repo = TickerRepository(session)
    ticker_obj = await ticker_repo.get_by_symbol(ticker)
    if not ticker_obj:
        raise HTTPException(status_code=404, detail=f"Ticker {ticker} nenalezen")

    news_repo = NewsRepository(session)
    items = await news_repo.get_news_list(
        ticker_id=ticker_obj.id,
        for_date=date_filter,
        limit=limit,
        offset=offset,
    )

    result = []
    for item in items:
        # Find the primary prediction (for the requested ticker)
        pred_by_ticker = {p.ticker_id: p for p in item.predictions}
        pred = pred_by_ticker.get(ticker_obj.id) or (item.predictions[0] if item.predictions else None)

        # Importance weight for the requested ticker
        weight = None
        for rel in item.ticker_relevances:
            if rel.ticker_id == ticker_obj.id:
                weight = rel.importance_weight
                break

        # Build per-ticker impact list (all associated tickers)
        ticker_impacts: list[TickerImpactOut] = []
        for rel in item.ticker_relevances:
            if not rel.ticker:
                continue
            p = pred_by_ticker.get(rel.ticker_id)
            ticker_impacts.append(TickerImpactOut(
                symbol=rel.ticker.symbol,
                prob_down=p.prob_down if p else 0.333,
                prob_neutral=p.prob_neutral if p else 0.334,
                prob_up=p.prob_up if p else 0.333,
                importance_weight=rel.importance_weight or 0.0,
                confidence=p.confidence if p else 0.0,
                llm_reasoning=p.llm_reasoning if p else None,
            ))

        result.append(NewsItemOut(
            id=item.id,
            title=item.title,
            body=item.body,
            url=item.url,
            published_at=item.published_at,
            source_name=item.source.name,
            importance_weight=weight,
            prediction=pred,
            ticker_impacts=ticker_impacts,
        ))
    return result


@router.get("/events/today", response_model=list[CalendarEventOut])
async def events_today(
    date_filter: date | None = Query(default=None, alias="date"),
    session: AsyncSession = Depends(get_session),
):
    repo = NewsRepository(session)
    items = await repo.get_high_impact_events(for_date=date_filter)
    result = []
    for item in items:
        cats = [ic.category.name for ic in item.categories if ic.category]
        max_w = max(
            (r.importance_weight for r in item.ticker_relevances if r.importance_weight is not None),
            default=0.0,
        )
        result.append(CalendarEventOut(
            id=item.id,
            title=item.title,
            published_at=item.published_at,
            categories=cats,
            max_weight=max_w,
        ))
    return result


@router.get("/{news_id}", response_model=NewsItemDetail)
async def get_news(news_id: int, session: AsyncSession = Depends(get_session)):
    repo = NewsRepository(session)
    item = await repo.get_news_by_id(news_id)
    if not item:
        raise HTTPException(status_code=404, detail="Zpráva nenalezena")

    pred = item.predictions[0] if item.predictions else None
    categories = [ic.category.name for ic in item.categories if ic.category]

    return NewsItemDetail(
        id=item.id,
        title=item.title,
        body=item.body,
        url=item.url,
        published_at=item.published_at,
        source_name=item.source.name,
        prediction=pred,
        categories=categories,
        key_drivers=[],
    )
