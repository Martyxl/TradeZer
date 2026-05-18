from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Sequence

from app.models import Ticker


class TickerRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all_enabled(self) -> Sequence[Ticker]:
        result = await self.session.execute(
            select(Ticker).where(Ticker.enabled.is_(True)).order_by(Ticker.id)
        )
        return result.scalars().all()

    async def get_by_symbol(self, symbol: str) -> Ticker | None:
        return await self.session.scalar(
            select(Ticker).where(Ticker.symbol == symbol)
        )

    async def get_by_id(self, ticker_id: int) -> Ticker | None:
        return await self.session.get(Ticker, ticker_id)
