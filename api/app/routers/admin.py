from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.schemas import RefreshResponse
from app.services.news_aggregator import NewsAggregator

router = APIRouter(prefix="/api", tags=["admin"])


def _verify_token(x_internal_token: str = Header(default="")):
    if settings.internal_api_token and x_internal_token != settings.internal_api_token:
        raise HTTPException(status_code=401, detail="Neplatný token")


@router.post("/refresh", response_model=RefreshResponse, dependencies=[Depends(_verify_token)])
async def manual_refresh(session: AsyncSession = Depends(get_session)):
    aggregator = NewsAggregator(session)
    stats = await aggregator.refresh()
    return RefreshResponse(status="ok", stats=stats)


@router.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
