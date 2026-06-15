"""ForexFactory adaptér — čte XML export ekonomického kalendáře.

Strategie external_id:
  - Před vydáním (actual = ""): id = hash(date+title+currency+"upcoming")
  - Po vydání (actual ≠ ""):  id = hash(date+title+currency+"actual:<value>")

Tím pádem každé vydání aktuálního čísla vytvoří NOVOU položku v DB
a okamžitě dostane LLM predikci s reálnými daty (actual vs. forecast).
"""
import hashlib
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.sources.base import NewsSource, RawNewsItem

log = structlog.get_logger(__name__)

# Originální ForexFactory URL je za Cloudflare — blokuje přímý přístup.
# Mirror na faireconomy.media je spolehlivý veřejný zrcadlový server.
FF_XML_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

# Zachycujeme pouze US, EU a China makro data
# GBP/JPY/CHF mají výrazně menší vliv na naše instrumenty (ES, NQ, XAUUSD)
TRACKED_CURRENCIES = {"USD", "EUR", "CNY"}

# Filtrujeme pouze medium a high impact (low = příliš šumu)
HIGH_MEDIUM_IMPACTS = {"high", "medium"}

# Mirror používá <country> místo <currency> a nemá pole <actual>
# (actual data přicházejí přes RSS kanály — investingLive, Reuters atd.)


async def get_upcoming_events(window_before_min: int = 120, window_after_min: int = 60) -> list[dict]:
    """Vrátí USD/EUR/CNY high/medium impact eventy v časovém okně kolem 'teď'.

    Používá se pro smart cron scheduling — zjistí jestli má cenu spouštět LLM predikce.
    Vrátí seznam eventů s UTC časem, měnou, dopadem a forecastem.
    """
    import httpx
    from app.config import settings

    try:
        headers = {"User-Agent": settings.forexfactory_user_agent}
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(FF_XML_URL, headers=headers)
            resp.raise_for_status()
            xml_text = resp.text
    except Exception as e:
        log.warning("get_upcoming_events: FF XML fetch failed", error=str(e))
        return []

    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []

    events_raw = root.findall("event")
    if not events_raw:
        for week in root.findall("week"):
            events_raw.extend(week.findall("event"))

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=window_after_min)
    window_end = now + timedelta(minutes=window_before_min)

    result = []
    for event in events_raw:
        ev: dict[str, str] = {}
        for child in event:
            ev[child.tag] = (child.text or "").strip()

        currency = ev.get("currency", "") or ev.get("country", "")
        if currency not in TRACKED_CURRENCIES:
            continue

        impact = (ev.get("impact", "") or "").lower()
        if impact not in HIGH_MEDIUM_IMPACTS:
            continue

        date_str = ev.get("date", "")
        time_str = ev.get("time", "")
        combined = f"{date_str} {time_str}".strip()
        try:
            if time_str:
                event_time = datetime.strptime(combined, "%m-%d-%Y %I:%M%p").replace(tzinfo=timezone.utc)
            else:
                event_time = datetime.strptime(date_str, "%m-%d-%Y").replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        if window_start <= event_time <= window_end:
            minutes_until = int((event_time - now).total_seconds() / 60)
            result.append({
                "title": ev.get("title", ""),
                "currency": currency,
                "impact": impact,
                "time_utc": event_time.strftime("%Y-%m-%dT%H:%M:00Z"),
                "minutes_until": minutes_until,
                "forecast": ev.get("forecast", ""),
                "previous": ev.get("previous", ""),
                "actual": ev.get("actual", ""),
            })

    result.sort(key=lambda e: e["minutes_until"])
    return result


class ForexFactoryAdapter(NewsSource):
    name = "forex_factory"
    source_weight = 1.0

    def _build_external_id(self, event: dict) -> str:
        """
        Dva různé external_id pro pre-event a post-event:
        - upcoming (bez actual): stabilní ID — uložíme jednou, neduplikujeme
        - po vydání (s actual):  nové ID obsahující actual — vytvoří novou položku
          s reálnými daty pro přesnou LLM predikci
        """
        date = event.get("date", "")
        title = event.get("title", "")
        currency = event.get("currency", "")
        actual = event.get("actual", "").strip()
        if actual:
            key = f"{date}-{title}-{currency}-actual:{actual}"
        else:
            key = f"{date}-{title}-{currency}-upcoming"
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
        actual = event.get("actual", "").strip()
        forecast = event.get("forecast", "").strip()
        previous = event.get("previous", "").strip()
        if actual:
            # Vydáno — klíčová informace: actual vs forecast
            parts.append(f"| Actual: {actual} | Forecast: {forecast or '?'} | Prev: {previous or '?'}")
        elif forecast:
            # Nadcházející — zobraz forecast jako kontext
            parts.append(f"| Upcoming | Forecast: {forecast} | Prev: {previous or '?'}")
        return " ".join(parts)

    def _build_body(self, event: dict) -> str:
        actual = event.get("actual", "").strip()
        status = "RELEASED" if actual else "UPCOMING"
        return (
            f"Status: {status}\n"
            f"Currency: {event.get('currency', 'N/A')}\n"
            f"Impact: {event.get('impact', 'N/A')}\n"
            f"Actual: {actual or 'N/A'}\n"
            f"Forecast: {event.get('forecast', 'N/A')}\n"
            f"Previous: {event.get('previous', 'N/A')}\n"
            f"Description: {event.get('description', 'N/A')}"
        )

    def _instruments_hint(self, currency: str) -> list[str]:
        """
        Mapování měny na relevantní instrumenty.
        USD data hýbou nejen forexem, ale i US akciovými indexy a zlatem.
        CNY data (Čína) silně ovlivňují zlato a globální poptávku.
        """
        if currency == "EUR":
            return ["EURUSD", "XAUUSD"]
        elif currency == "USD":
            return ["EURUSD", "GBPUSD", "USDJPY", "ES", "NQ", "XAUUSD"]
        elif currency == "CNY":
            # Čínská makro data (PMI, GDP, trade balance) ovlivňují zlato a indexy
            return ["XAUUSD", "ES", "NQ"]
        return ["EURUSD"]

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

        skipped_low = 0
        # Mirror XML používá <event> přímo pod root (ne přes <week>)
        # Zkus oba formáty: s <week> obalem (originální FF) i bez (mirror)
        events = root.findall("event")
        if not events:
            for week in root.findall("week"):
                events.extend(week.findall("event"))

        for event in events:
                event_dict: dict[str, str] = {}
                for child in event:
                    event_dict[child.tag] = (child.text or "").strip()

                # Mirror: <country> místo <currency>
                currency = event_dict.get("currency", "") or event_dict.get("country", "")
                if currency not in TRACKED_CURRENCIES:
                    continue

                # Filtruj low-impact eventy — příliš šumu, minimální pohyb trhu
                impact = self._parse_impact(event_dict.get("impact", ""))
                if impact not in HIGH_MEDIUM_IMPACTS:
                    skipped_low += 1
                    continue

                # Mirror má oddělené <date> a <time> (není kombinovaný string)
                date_str = event_dict.get("date", "")
                time_str = event_dict.get("time", "")
                combined = f"{date_str} {time_str}".strip()
                try:
                    if time_str:
                        published_at = datetime.strptime(combined, "%m-%d-%Y %I:%M%p").replace(
                            tzinfo=timezone.utc
                        )
                    else:
                        published_at = datetime.strptime(date_str, "%m-%d-%Y").replace(
                            tzinfo=timezone.utc
                        )
                except ValueError:
                    published_at = datetime.now(timezone.utc)

                ext_id = self._build_external_id(event_dict)
                actual_present = bool(event_dict.get("actual", "").strip())
                instruments = self._instruments_hint(currency)

                items.append(
                    RawNewsItem(
                        source=self.name,
                        external_id=ext_id,
                        title=self._build_title(event_dict),
                        body=self._build_body(event_dict),
                        url=FF_XML_URL,
                        published_at=published_at,
                        # instruments_hint MUSÍ být v raw_payload — pouze ten se ukládá do DB
                        # a čte se zpět v predict_pending přes item.raw_payload.get("instruments_hint")
                        raw_payload={
                            **event_dict,
                            "actual_present": actual_present,
                            "instruments_hint": instruments,
                        },
                        instruments_hint=instruments,
                    )
                )

        log.info(
            "ForexFactory fetch complete",
            count=len(items),
            skipped_low_impact=skipped_low,
        )
        return items
