"""AlphaVantage NEWS_SENTIMENT adaptér."""
import hashlib
from datetime import datetime

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.sources.base import NewsSource, RawNewsItem

log = structlog.get_logger(__name__)

AV_BASE = "https://www.alphavantage.co/query"
FOREX_TOPICS = "forex,economy_fiscal,economy_monetary,economy_macro"


class AlphaVantageAdapter(NewsSource):
    name = "alphavantage"
    source_weight = 0.6

    def is_available(self) -> bool:
        return bool(settings.alphavantage_api_key)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
    async def _fetch(self) -> list[dict]:
        params = {
            "function": "NEWS_SENTIMENT",
            "topics": FOREX_TOPICS,
            "sort": "LATEST",
            "limit": "50",
            "apikey": settings.alphavantage_api_key,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(AV_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("feed", [])

    def _external_id(self, item: dict) -> str:
        key = item.get("url", "") or item.get("title", "")
        return hashlib.sha256(key.encode()).hexdigest()[:32]

    async def fetch(self) -> list[RawNewsItem]:
        if not self.is_available():
            log.info("AlphaVantage přeskočen — chybí API klíč")
            return []

        log.info("AlphaVantage fetch start")
        try:
            articles = await self._fetch()
        except Exception as e:
            log.error("AlphaVantage fetch failed", error=str(e))
            return []

        items: list[RawNewsItem] = []
        for article in articles:
            time_str = article.get("time_published", "")
            try:
                published_at = datetime.strptime(time_str, "%Y%m%dT%H%M%S")
            except ValueError:
                published_at = datetime.utcnow()

            items.append(RawNewsItem(
                source=self.name,
                external_id=self._external_id(article),
                title=article.get("title", ""),
                body=article.get("summary"),
                url=article.get("url", ""),
                published_at=published_at,
                raw_payload=article,
                instruments_hint=["EURUSD"],
            ))

        log.info("AlphaVantage fetch complete", count=len(items))
        return items
