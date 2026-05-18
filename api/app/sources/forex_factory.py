"""ForexFactory adaptér — čte XML export ekonomického kalendáře."""
import hashlib
from datetime import datetime, timezone
from xml.etree import ElementTree

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.sources.base import NewsSource, RawNewsItem

log = structlog.get_logger(__name__)

FF_XML_URL = "https://www.forexfactory.com/ff_calendar_thisweek.xml"

EUR_CURRENCIES = {"EUR", "USD", "GBP", "JPY", "CHF"}


class ForexFactoryAdapter(NewsSource):
    name = "forex_factory"
    source_weight = 1.0

    def _build_external_id(self, event: dict) -> str:
        key = f"{event.get('date', '')}-{event.get('title', '')}-{event.get('currency', '')}"
        return hashlib.sha256(key.encode()).hexdigest()[:32]

    def _parse_impact(self, impact_str: str) -> str:
        return impact_str.lower() if impact_str else "low"

    def _build_title(self, event: dict) -> str:
        parts = []
        if event.get("currency"):
            parts.append(f"[{event['currency']}]")
        parts.append(event.get("title", "Unknown Event"))
        impact = self._parse_impact(event.get("impact", ""))
        if impact == "high":
            parts.append("⚡ HIGH IMPACT")
        actual = event.get("actual", "")
        forecast = event.get("forecast", "")
        previous = event.get("previous", "")
        if actual or forecast:
            parts.append(f"| Actual: {actual or '?'} | Forecast: {forecast or '?'} | Prev: {previous or '?'}")
        return " ".join(parts)

    def _build_body(self, event: dict) -> str:
        return (
            f"Currency: {event.get('currency', 'N/A')}\n"
            f"Impact: {event.get('impact', 'N/A')}\n"
            f"Actual: {event.get('actual', 'N/A')}\n"
            f"Forecast: {event.get('forecast', 'N/A')}\n"
            f"Previous: {event.get('previous', 'N/A')}\n"
            f"Description: {event.get('description', 'N/A')}"
        )

    def _instruments_hint(self, currency: str) -> list[str]:
        hints = []
        if currency == "EUR":
            hints.extend(["EURUSD", "EURGBP", "EURJPY"])
        elif currency == "USD":
            hints.extend(["EURUSD", "GBPUSD", "USDJPY"])
        elif currency == "GBP":
            hints.extend(["GBPUSD", "EURGBP"])
        elif currency == "JPY":
            hints.extend(["USDJPY", "EURJPY"])
        return hints

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _download_xml(self) -> str:
        headers = {"User-Agent": settings.forexfactory_user_agent}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(FF_XML_URL, headers=headers)
            resp.raise_for_status()
            return resp.text

    async def fetch(self) -> list[RawNewsItem]:
        log.info("ForexFactory fetch start")
        try:
            xml_text = await self._download_xml()
        except Exception as e:
            log.error("ForexFactory fetch failed", error=str(e))
            return []

        items: list[RawNewsItem] = []
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError as e:
            log.error("ForexFactory XML parse error", error=str(e))
            return []

        for week in root.findall("week"):
            for event in week.findall("event"):
                event_dict: dict[str, str] = {}
                for child in event:
                    event_dict[child.tag] = (child.text or "").strip()

                currency = event_dict.get("currency", "")
                if currency not in EUR_CURRENCIES:
                    continue

                published_str = event_dict.get("date", "")
                try:
                    published_at = datetime.strptime(published_str, "%m-%d-%Y %I:%M%p").replace(
                        tzinfo=timezone.utc
                    )
                except ValueError:
                    published_at = datetime.now(timezone.utc)

                ext_id = self._build_external_id(event_dict)
                items.append(
                    RawNewsItem(
                        source=self.name,
                        external_id=ext_id,
                        title=self._build_title(event_dict),
                        body=self._build_body(event_dict),
                        url=FF_XML_URL,
                        published_at=published_at,
                        raw_payload=event_dict,
                        instruments_hint=self._instruments_hint(currency),
                    )
                )

        log.info("ForexFactory fetch complete", count=len(items))
        return items
