"""Generický RSS adaptér — feedparser."""
import hashlib
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from app.sources.base import NewsSource, RawNewsItem

log = structlog.get_logger(__name__)

DEFAULT_FEEDS = [
    # ── Původní zdroje ──────────────────────────────────────────────────────
    {
        "name": "rss_reuters",
        "url": "https://feeds.reuters.com/reuters/businessNews",
        "source_weight": 0.5,
        "instruments_hint": [],  # auto-detected from keywords
    },
    {
        "name": "rss_ecb",
        "url": "https://www.ecb.europa.eu/rss/press.html",
        "source_weight": 0.9,
        "instruments_hint": ["EURUSD"],
    },
    {
        "name": "rss_fxstreet_gold",
        "url": "https://www.fxstreet.com/rss/analysis/commodities",
        "source_weight": 0.75,
        "instruments_hint": ["XAUUSD"],
    },
    {
        "name": "rss_mining",
        "url": "https://www.mining.com/feed/",
        "source_weight": 0.65,
        "instruments_hint": ["XAUUSD"],
    },
    {
        "name": "rss_cnbc_markets",
        "url": "https://www.cnbc.com/id/20910258/device/rss/rss.html",
        "source_weight": 0.75,
        "instruments_hint": ["ES"],
    },
    {
        "name": "rss_cnbc_tech",
        "url": "https://www.cnbc.com/id/19854910/device/rss/rss.html",
        "source_weight": 0.70,
        "instruments_hint": ["NQ"],
    },
    # ── Nové zdroje ──────────────────────────────────────────────────────────
    # Investinglive (dříve ForexLive) — rychlé breaking forex news
    {
        "name": "rss_investinglive",
        "url": "https://investinglive.com/feed/news",
        "source_weight": 0.85,
        "instruments_hint": [],  # pokrývá vše — auto-detect
    },
    # FXStreet — obecné FX zprávy (jiný feed než gold analysis)
    {
        "name": "rss_fxstreet_news",
        "url": "https://www.fxstreet.com/rss/news",
        "source_weight": 0.80,
        "instruments_hint": [],
    },
    # CoinDesk — crypto/Bitcoin
    {
        "name": "rss_coindesk",
        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "source_weight": 0.80,
        "instruments_hint": ["BTCUSD"],
    },
    # MarketPulse (OANDA) — forex, gold, akcie — 10 kvalitních článků
    {
        "name": "rss_marketpulse",
        "url": "https://www.marketpulse.com/feed/",
        "source_weight": 0.80,
        "instruments_hint": [],
    },
    # ActionForex — forex analýza EUR/USD, GBP/USD, USD/JPY
    {
        "name": "rss_actionforex",
        "url": "https://www.actionforex.com/feed/",
        "source_weight": 0.70,
        "instruments_hint": [],
    },
]


class RSSAdapter(NewsSource):
    name: str
    source_weight: float

    def __init__(self, name: str, url: str, source_weight: float = 0.5,
                 instruments_hint: list[str] | None = None):
        self.name = name
        self.url = url
        self.source_weight = source_weight
        self._instruments_hint = instruments_hint or []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _fetch_feed(self) -> Any:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; Tradezer/1.0; RSS reader)"}
        async with httpx.AsyncClient(timeout=20.0, headers=headers, follow_redirects=True) as client:
            resp = await client.get(self.url)
            resp.raise_for_status()
            return feedparser.parse(resp.text)

    def _parse_date(self, entry: Any) -> datetime:
        for attr in ("published", "updated"):
            val = getattr(entry, attr, None)
            if val:
                try:
                    return parsedate_to_datetime(val).astimezone(timezone.utc).replace(tzinfo=None)
                except Exception:
                    pass
        return datetime.utcnow()

    def _external_id(self, entry: Any) -> str:
        key = getattr(entry, "id", None) or getattr(entry, "link", "") or entry.get("title", "")
        return hashlib.sha256(key.encode()).hexdigest()[:32]

    async def fetch(self) -> list[RawNewsItem]:
        log.info("RSS fetch start", source=self.name, url=self.url)
        try:
            feed = await self._fetch_feed()
        except Exception as e:
            log.error("RSS fetch failed", source=self.name, error=str(e))
            return []

        items: list[RawNewsItem] = []
        for entry in feed.entries:
            title = getattr(entry, "title", "") or ""
            if not title:
                continue
            body = getattr(entry, "summary", None) or getattr(entry, "description", None)
            link = getattr(entry, "link", "") or self.url

            items.append(RawNewsItem(
                source=self.name,
                external_id=self._external_id(entry),
                title=title,
                body=body,
                url=link,
                published_at=self._parse_date(entry),
                raw_payload={"feed_id": getattr(entry, "id", ""), "link": link},
                instruments_hint=self._instruments_hint,
            ))

        log.info("RSS fetch complete", source=self.name, count=len(items))
        return items


def build_default_rss_adapters() -> list[RSSAdapter]:
    return [RSSAdapter(**feed) for feed in DEFAULT_FEEDS]
