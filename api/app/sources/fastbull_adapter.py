"""FastBull adaptér — scrapeuje news feed z fastbull.com.

FastBull nemá veřejné RSS ani dokumentované API.
Adaptér volá interní endpoint který stránka používá při načítání.
Pokud endpoint selže (403/404), vrátí prázdný seznam bez pádu systému.
"""
import hashlib
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

from app.sources.base import NewsSource, RawNewsItem

log = structlog.get_logger(__name__)

# Kategorie → ticker hint mapping
CATEGORY_TICKER_MAP: dict[str, list[str]] = {
    "gold": ["XAUUSD"],
    "precious": ["XAUUSD"],
    "forex": ["EURUSD"],
    "currency": ["EURUSD"],
    "bitcoin": ["BTCUSD"],
    "crypto": ["BTCUSD"],
    "nasdaq": ["NQ"],
    "s&p": ["ES"],
    "stocks": ["ES"],
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.fastbull.com/",
    "Origin": "https://www.fastbull.com",
}

# Kandidáti na API endpoint — zkusíme postupně
API_CANDIDATES = [
    "https://www.fastbull.com/api/v1/news/list",
    "https://www.fastbull.com/api/news",
    "https://api.fastbull.com/v1/news/list",
]


def _parse_timestamp(val: Any) -> datetime:
    """Parsuje Unix timestamp nebo ISO string na datetime UTC."""
    if val is None:
        return datetime.utcnow()
    try:
        if isinstance(val, (int, float)):
            # Unix timestamp — může být v ms nebo s
            ts = val / 1000 if val > 1e10 else val
            return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
        if isinstance(val, str):
            for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                try:
                    return datetime.strptime(val, fmt)
                except ValueError:
                    continue
    except Exception:
        pass
    return datetime.utcnow()


def _detect_tickers(title: str, category: str) -> list[str]:
    text = (title + " " + category).lower()
    for keyword, tickers in CATEGORY_TICKER_MAP.items():
        if keyword in text:
            return tickers
    return []


class FastBullAdapter(NewsSource):
    name = "fastbull"
    source_weight = 0.75

    async def fetch(self) -> list[RawNewsItem]:
        log.info("FastBull fetch start")

        for endpoint in API_CANDIDATES:
            try:
                items = await self._try_endpoint(endpoint)
                if items is not None:
                    log.info("FastBull fetch OK", endpoint=endpoint, count=len(items))
                    return items
            except Exception as e:
                log.debug("FastBull endpoint failed", endpoint=endpoint, error=str(e))

        log.warning("FastBull: všechny endpointy selhaly, zdroj přeskočen")
        return []

    async def _try_endpoint(self, url: str) -> list[RawNewsItem] | None:
        params = {"pageNum": 1, "pageSize": 30, "type": "all", "lang": "en"}
        async with httpx.AsyncClient(timeout=15.0, headers=HEADERS,
                                     follow_redirects=True) as client:
            resp = await client.get(url, params=params)
            if resp.status_code in (403, 404, 405):
                return None
            resp.raise_for_status()
            data = resp.json()

        # Různé struktury podle endpointu
        raw_list: list[dict] = []
        if isinstance(data, list):
            raw_list = data
        elif isinstance(data, dict):
            for key in ("data", "list", "items", "news", "result"):
                candidate = data.get(key)
                if isinstance(candidate, list):
                    raw_list = candidate
                    break
                if isinstance(candidate, dict):
                    for sub in ("list", "items", "data"):
                        if isinstance(candidate.get(sub), list):
                            raw_list = candidate[sub]
                            break
                    if raw_list:
                        break

        if not raw_list:
            return None  # Neznámá struktura → zkusit další endpoint

        items: list[RawNewsItem] = []
        for entry in raw_list:
            title = (entry.get("title") or entry.get("headline") or "").strip()
            if not title:
                continue

            body = entry.get("summary") or entry.get("content") or entry.get("description")
            url_val = entry.get("url") or entry.get("link") or entry.get("articleUrl") or ""
            category = str(entry.get("category") or entry.get("tag") or "")
            published_raw = (entry.get("publishTime") or entry.get("publishedAt")
                             or entry.get("time") or entry.get("created_at"))

            external_id = hashlib.sha256(
                (entry.get("id") or url_val or title).encode()
            ).hexdigest()[:32]

            items.append(RawNewsItem(
                source=self.name,
                external_id=external_id,
                title=title,
                body=body,
                url=url_val or "https://www.fastbull.com/news",
                published_at=_parse_timestamp(published_raw),
                raw_payload={"category": category, "raw": entry},
                instruments_hint=_detect_tickers(title, category),
            ))

        return items
