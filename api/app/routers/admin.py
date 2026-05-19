import os

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.schemas import RefreshResponse
from app.services.news_aggregator import NewsAggregator

router = APIRouter(prefix="/api", tags=["admin"])


def _verify_token(
    x_internal_token: str = Header(default=""),
    authorization: str = Header(default=""),
):
    # Accept X-Internal-Token (manual calls, cron-job.org)
    if settings.internal_api_token and x_internal_token == settings.internal_api_token:
        return
    # Accept Vercel cron: Authorization: Bearer <CRON_SECRET>
    cron_secret = os.environ.get("CRON_SECRET", "")
    if cron_secret and authorization == f"Bearer {cron_secret}":
        return
    # Reject if token is configured but nothing matched
    if settings.internal_api_token:
        raise HTTPException(status_code=401, detail="Neplatný token")


@router.post("/refresh", response_model=RefreshResponse, dependencies=[Depends(_verify_token)])
async def manual_refresh(
    session: AsyncSession = Depends(get_session),
    max_predictions: int = Query(default=8, ge=1, le=50),
):
    aggregator = NewsAggregator(session)
    stats = await aggregator.refresh(max_predictions=max_predictions)
    return RefreshResponse(status="ok", stats=stats)


@router.post("/predict", dependencies=[Depends(_verify_token)])
async def predict_pending(
    session: AsyncSession = Depends(get_session),
    max_predictions: int = Query(default=8, ge=1, le=30),
):
    """Spustí LLM predikce pro položky bez predikcí (bez RSS fetche — rychlejší)."""
    aggregator = NewsAggregator(session)
    stats = await aggregator.predict_pending(max_predictions=max_predictions)
    return {"status": "ok", "stats": stats}


@router.post("/calibrate", dependencies=[Depends(_verify_token)])
async def calibrate(
    session: AsyncSession = Depends(get_session),
):
    """Stáhne tržní ceny a zaznamená market reactions pro predikce starší 15 min."""
    from app.services.calibration_service import CalibrationService
    service = CalibrationService(session)
    stats = await service.run()
    return {"status": "ok", "stats": stats}


@router.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
