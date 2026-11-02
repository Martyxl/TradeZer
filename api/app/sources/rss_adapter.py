"""Generický RSS adaptér — feedparser."""
import hashlib
import html
import re
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
    # Seznam ověřen 2026-10-16 živou zkouškou Z PROSTŘEDÍ VERCELU (`POST /api/sources/check`).
    # Kontrola zdrojů: `GET /api/sources/health` (kolik zpráv který zdroj uložil za 24 h; 0 = mrtvý).
    # ODSTRANĚNO (trvale mrtvé): rss_reuters (feeds.reuters.com zanikl), rss_fxstreet_news/_gold
    # (HTTP 403 — FXStreet blokuje IP Vercelu), rss_ecb/coindesk/actionforex (nesledované instrumenty),
    # rss_seekingalpha (funguje, ale jde o zprávy k jednotlivým akciím → 0 relevantních položek).
    # Google News RSS záměrně NENÍ (podmínky nejsou vhodné pro komerční službu). BLS feed = 403.
    #
    # instruments_hint: [] = relevanci určí klíčová slova (+ geopolitika); explicitní seznam = vše
    # z feedu je relevantní pro tyto instrumenty (centrální banka, zlato).

    # ── Centrální banka (vysoký dopad na všechny sledované instrumenty) ────────
    {
        "name": "rss_fed_press",
        "url": "https://www.federalreserve.gov/feeds/press_all.xml",
        "source_weight": 0.95,
        "instruments_hint": ["NQ", "ES", "YM", "XAUUSD"],
        "max_items": 8,
    },
    {
        "name": "rss_fed_speeches",
        "url": "https://www.federalreserve.gov/feeds/speeches.xml",
        "source_weight": 0.90,
        "instruments_hint": ["NQ", "ES", "YM", "XAUUSD"],
        "max_items": 8,
    },
    # ── Zlato ────────────────────────────────────────────────────────────────
    {
        "name": "rss_mining",
        "url": "https://www.mining.com/feed/",
        "source_weight": 0.65,
        "instruments_hint": ["XAUUSD"],
    },
    {
        "name": "rss_mining_gold",
        "url": "https://www.mining.com/commodity/gold/feed/",
        "source_weight": 0.70,
        "instruments_hint": ["XAUUSD"],
    },
    # ── Trhy a makro (auto-detekce přes klíčová slova) ─────────────────────────
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
    {
        "name": "rss_cnbc_top",
        "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "source_weight": 0.70,
        "instruments_hint": [],
    },
    {
        "name": "rss_cnbc_investing",
        "url": "https://www.cnbc.com/id/15839069/device/rss/rss.html",
        "source_weight": 0.70,
        "instruments_hint": [],
    },
    # Investinglive (dříve ForexLive) — rychlé breaking news
    {
        "name": "rss_investinglive",
        "url": "https://investinglive.com/feed/news",
        "source_weight": 0.85,
        "instruments_hint": [],
    },
    # MarketPulse (OANDA) — forex, zlato, akcie
    {
        "name": "rss_marketpulse",
        "url": "https://www.marketpulse.com/feed/",
        "source_weight": 0.80,
        "instruments_hint": [],
    },
    {
        "name": "rss_marketwatch",
        "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        "source_weight": 0.75,
        "instruments_hint": [],
    },
    {
        "name": "rss_nasdaq",
        "url": "https://www.nasdaq.com/feed/rssoutbound?category=Markets",
        "source_weight": 0.70,
        "instruments_hint": [],
    },
    {
        "name": "rss_ft_markets",
        "url": "https://www.ft.com/markets?format=rss",
        "source_weight": 0.80,
        "instruments_hint": [],
    },
    {
        "name": "rss_nyt_business",
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
        "source_weight": 0.70,
        "instruments_hint": [],
    },
    # Energie / ropa — geopolitický šok (Hormuz, OPEC…) se propíše do všech indexů i zlata
    {
        "name": "rss_oilprice",
        "url": "https://oilprice.com/rss/main",
        "source_weight": 0.60,
        "instruments_hint": [],
    },
]

class RSSAdapter(NewsSource):
    name: str
    source_weight: float

    def __init__(self, name: str, url: str, source_weight: float = 0.5,
                 instruments_hint: list[str] | None = None, max_items: int = 15):
        self.name = name
        self.url = url
        self.source_weight = source_weight
        self._instruments_hint = instruments_hint or []
        self._max_items = max_items

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

        items = items[: self._max_items]
        log.info("RSS fetch complete", source=self.name, count=len(items))
        return items


class InvestingLiveAdapter(RSSAdapter):
    """investingLive: RSS + titulky z homepage.

    RSS feed se u nich generuje se zpožděním až ~1 h (2. 11. 2026: ISM v 15:00 UTC na webu hned,
    v RSS ani po 25 min), kdežto homepage má cache 30 s. Vydání maker („55.5 versus 54.5 estimate“)
    potřebujeme do pár minut → doplníme položky z homepage. ID = hash URL článku, stejně jako u RSS
    (guid = URL), takže až článek dorazí i v RSS, neuloží se podruhé.
    """

    HOME_URL = "https://investinglive.com/"
    _SLOT = re.compile(r'href="(/news/[^"]+?)/?"[^>]*>\s*<h3[^>]*articleSlotHeader__title[^>]*>(.*?)</h3>', re.S)
    _TIME = re.compile(r'<time dateTime="([^"]+)"')

    async def _fetch_home(self) -> str:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; Tradezer/1.0; RSS reader)"}
        async with httpx.AsyncClient(timeout=20.0, headers=headers, follow_redirects=True) as client:
            resp = await client.get(self.HOME_URL)
            resp.raise_for_status()
            return resp.text

    @classmethod
    def parse_home(cls, page: str, base: str = "https://investinglive.com") -> list[dict]:
        """[{url, title, published_at}] — jen články s titulkem i časem vydání."""
        out, seen = [], set()
        slots = list(cls._SLOT.finditer(page))
        for i, m in enumerate(slots):
            url = f"{base}{m.group(1)}/"
            if url in seen:
                continue
            end = slots[i + 1].start() if i + 1 < len(slots) else m.end() + 6000
            t = cls._TIME.search(page, m.end(), end)
            title = html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
            if not t or not title:
                continue
            try:
                raw = re.sub(r"(\.\d{6})\d+", r"\1", t.group(1)).replace("Z", "+00:00")
                ts = datetime.fromisoformat(raw).astimezone(timezone.utc).replace(tzinfo=None)
            except ValueError:
                continue
            seen.add(url)
            out.append({"url": url, "title": title, "published_at": ts})
        return out

    async def fetch(self) -> list[RawNewsItem]:
        items = await super().fetch()
        try:
            page = await self._fetch_home()
        except Exception as e:  # noqa: BLE001 — homepage je jen doplněk RSS
            log.warning("investingLive homepage fetch failed", error=str(e)[:200])
            return items
        known = {i.external_id for i in items}
        newest = max((i.published_at for i in items), default=datetime.min)
        extra = []
        for a in self.parse_home(page):
            ext = hashlib.sha256(a["url"].encode()).hexdigest()[:32]
            if ext in known or a["published_at"] <= newest:
                continue  # RSS už článek má (nebo je starší než nejnovější z RSS)
            known.add(ext)
            extra.append(RawNewsItem(
                source=self.name, external_id=ext, title=a["title"], body=None, url=a["url"],
                published_at=a["published_at"],
                raw_payload={"feed_id": a["url"], "link": a["url"], "via": "homepage"},
                instruments_hint=self._instruments_hint,
            ))
        if extra:
            log.info("investingLive homepage extra", count=len(extra))
        return extra + items


def build_default_rss_adapters() -> list[RSSAdapter]:
    return [(InvestingLiveAdapter if feed["name"] == "rss_investinglive" else RSSAdapter)(**feed)
            for feed in DEFAULT_FEEDS]
