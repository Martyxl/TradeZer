"""SSE stream pro live updates."""
import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.repositories import NewsRepository, TickerRepository

router = APIRouter(prefix="/api/stream", tags=["stream"])


# Max. doba jednoho spojení. Na Vercelu každá vteřina otevřeného streamu = čas funkce (kvóta Active CPU
# / paměť). Frontend SSE už nepoužívá (dotazuje keširovaný /api/dashboard); endpoint zůstává jen pro
# staré otevřené záložky a končí brzy.
STREAM_MAX_SECONDS = 20


async def _event_generator(ticker_id: int, session: AsyncSession):
    import time
    started = time.monotonic()
    repo = NewsRepository(session)
    last_id = 0
    while time.monotonic() - started < STREAM_MAX_SECONDS:
        items = await repo.get_news_list(ticker_id=ticker_id, limit=5)
        if items:
            newest_id = max(i.id for i in items)
            if newest_id > last_id:
                for item in items:
                    if item.id > last_id:
                        pred = item.predictions[0] if item.predictions else None
                        data = {
                            "id": item.id,
                            "title": item.title,
                            "published_at": item.published_at.isoformat(),
                            "source": item.source.name,
                            "prediction": {
                                "prob_down": pred.prob_down if pred else None,
                                "prob_neutral": pred.prob_neutral if pred else None,
                                "prob_up": pred.prob_up if pred else None,
                            } if pred else None,
                        }
                        yield f"data: {json.dumps(data)}\n\n"
                last_id = newest_id
        await asyncio.sleep(min(30, max(0.0, STREAM_MAX_SECONDS - (time.monotonic() - started))))


@router.get("")
async def stream_news(
    ticker: str = Query(default="EURUSD"),
    session: AsyncSession = Depends(get_session),
):
    ticker_repo = TickerRepository(session)
    ticker_obj = await ticker_repo.get_by_symbol(ticker)
    if not ticker_obj:
        return {"error": "Ticker not found"}

    return StreamingResponse(
        _event_generator(ticker_obj.id, session),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
