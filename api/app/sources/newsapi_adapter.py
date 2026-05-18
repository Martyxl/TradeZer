"""NewsAPI adaptér."""
import hashlib
from datetime import datetime, timezone

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.sources.base import NewsSource, RawNewsItem

log = structlog.get_logger(__name__)

NEWSAPI_BASE = "https://newsapi.org/v2/everything"
FOREX_KEYWORDS = "ECB OR Fed OR inflation OR NFP OR \"EUR USD\" OR eurozone OR \"interest rate\" OR CPI OR \"monetary policy\""


class NewsAPIAdapter(NewsSource):
    name = "newsapi"
    source_weight = 0.7

    def is_available(self) -> bool:
        return bool(settings.newsapi_key)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
    async def _call_api(self) -> list[dict]:
        headers = {"X-Api-Key": settings.newsapi_key}
        params = {
            "q": FOREX_KEYWORDS,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 100,
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(NEWSAPI_BASE, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("articles", [])

    def _external_id(self, article: dict) -> str:
        key = article.get("url", "") or article.get("title", "")
        return hashlib.sha256(key.encode()).hexdigest()[:32]

    async def fetch(self) -> list[RawNewsItem]:
        if not self.is_available():
            log.info("NewsAPI přeskočen — chybí API klíč")
            return []

        log.info("NewsAPI fetch start")
        try:
            articles = await self._call_api()
        except Exception as e:
            log.error("NewsAPI fetch failed", error=str(e))
            return []

        items: list[RawNewsItem] = []
        for article in articles:
            published_str = article.get("publishedAt", "")
            try:
                published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                published_at = datetime.utcnow()

            items.append(RawNewsItem(
                source=self.name,
                external_id=self._external_id(article),
                title=article.get("title", ""),
                body=article.get("description") or article.get("content"),
                url=article.get("url", ""),
                published_at=published_at,
                raw_payload=article,
                instruments_hint=["EURUSD"],
            ))

        log.info("NewsAPI fetch complete", count=len(items))
        return items
