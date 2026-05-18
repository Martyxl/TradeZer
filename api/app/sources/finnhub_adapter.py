"""Finnhub adaptér."""
import hashlib
from datetime import datetime

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.sources.base import NewsSource, RawNewsItem

log = structlog.get_logger(__name__)

FINNHUB_BASE = "https://finnhub.io/api/v1"


class FinnhubAdapter(NewsSource):
    name = "finnhub"
    source_weight = 0.6

    def is_available(self) -> bool:
        return bool(settings.finnhub_api_key)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
    async def _fetch_forex_news(self) -> list[dict]:
        params = {"category": "forex", "token": settings.finnhub_api_key}
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(f"{FINNHUB_BASE}/news", params=params)
            resp.raise_for_status()
            return resp.json()

    def _external_id(self, item: dict) -> str:
        key = str(item.get("id", "")) or item.get("url", "") or item.get("headline", "")
        return hashlib.sha256(key.encode()).hexdigest()[:32]

    async def fetch(self) -> list[RawNewsItem]:
        if not self.is_available():
            log.info("Finnhub přeskočen — chybí API klíč")
            return []

        log.info("Finnhub fetch start")
        try:
            articles = await self._fetch_forex_news()
        except Exception as e:
            log.error("Finnhub fetch failed", error=str(e))
            return []

        items: list[RawNewsItem] = []
        for article in articles:
            ts = article.get("datetime", 0)
            published_at = datetime.utcfromtimestamp(ts) if ts else datetime.utcnow()

            items.append(RawNewsItem(
                source=self.name,
                external_id=self._external_id(article),
                title=article.get("headline", ""),
                body=article.get("summary"),
                url=article.get("url", ""),
                published_at=published_at,
                raw_payload=article,
                instruments_hint=["EURUSD"],
            ))

        log.info("Finnhub fetch complete", count=len(items))
        return items
