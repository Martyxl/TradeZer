from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.repositories import TickerRepository
from app.schemas import TickerOut

router = APIRouter(prefix="/api/tickers", tags=["tickers"])


@router.get("", response_model=list[TickerOut])
async def list_tickers(session: AsyncSession = Depends(get_session)):
    repo = TickerRepository(session)
    tickers = await repo.get_all_enabled()
    return tickers
