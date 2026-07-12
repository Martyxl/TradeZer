"""News agregátor — orchestruje fetch ze všech zdrojů a ukládá do DB."""
import asyncio
from typing import Sequence

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Ticker
from app.repositories import NewsRepository, TickerRepository
from app.services.prediction_engine import PredictionEngine
from app.sources import (
    ForexFactoryAdapter,
    build_default_rss_adapters,
    NewsAPIAdapter,
    FinnhubAdapter,
    AlphaVantageAdapter,
    RawNewsItem,
)
from app.sources.base import NewsSource

log = structlog.get_logger(__name__)

# Keywords mapped to ticker symbols — used when a source has no instruments_hint.
# Pořadí je důležité: specifičtější tickery (NQ/ES) mají přednost před obecnými (EURUSD).
# US makro data (PMI, NFP, CPI...) hýbou akciemi STEJNĚ SILNĚ jako forexem.
KEYWORD_TICKER_MAP: dict[str, list[str]] = {
    "XAUUSD": [
        "gold", "xau", "bullion", "precious metal", "precious metals",
        "gold price", "gold futures", "gold market", "gold rally",
        "silver price", "silver futures",
    ],
    "BTCUSD": ["bitcoin", "btc", "crypto", "cryptocurrency", "ethereum", "digital asset"],

    # US akciové indexy — US makro data, Fed, firemní výsledky
    "ES": [
        "s&p 500", "s&p500", "spx", "wall street", "dow jones", "nyse",
        "u.s. stocks", "us stocks", "u.s. equities", "stock market",
        # US makro — silný vliv na indexy
        "non-farm payroll", "nonfarm payroll", "nfp", "jobs report",
        "u.s. gdp", "us gdp", "gdp growth",
        "fed rate", "fomc", "federal reserve", "powell",
        "u.s. inflation", "us inflation", "core cpi", "core pce",
        "ism manufacturing", "ism services", "ism pmi",
        "u.s. retail sales", "us retail sales",
        "consumer confidence", "consumer sentiment",
        # Housing market — silně koreluje se sazbami → akcie
        "housing starts", "building permits", "existing home sales",
        "new home sales", "pending home sales",
        "u.s. housing", "us housing", "housing market",
        # Průmyslová a pracovní data
        "industrial production", "capacity utilization",
        "durable goods", "factory orders",
        "jobless claims", "unemployment claims", "initial claims",
        "adp employment", "adp jobs", "jolts", "job openings",
        # Ostatní klíčová US data
        "trade deficit", "u.s. trade", "us trade balance",
        "pce deflator", "personal income", "personal spending",
    ],
    "NQ": [
        "nasdaq", "tech sector", "tech stocks", "big tech", "faang", "magnificent",
        "apple", "microsoft", "nvidia", "meta", "alphabet", "amazon", "tesla",
        # NQ také reaguje na US makro (s větší volatilitou než ES)
        "non-farm payroll", "nonfarm payroll", "nfp",
        "fed rate", "fomc", "federal reserve",
        "u.s. inflation", "us inflation", "core cpi", "core pce",
        "ism manufacturing", "ism services",
        "manufacturing pmi", "services pmi",
        # Housing/claims ovlivňuje NQ přes sazby (mortgage → tech valuace)
        "housing starts", "building permits",
        "jobless claims", "initial claims", "adp employment",
    ],

    # Forex
    "EURUSD": [
        "european central bank", "ecb ", "eurozone", "euro area",
        "lagarde", "eur/usd", "euro/dollar",
        "eurozone pmi", "eurozone manufacturing", "eurozone services",
        "german", "france gdp", "italy gdp",
    ],
    "GBPUSD": [
        "bank of england", "boe", "gbp/usd", "pound", "sterling",
        "uk inflation", "uk gdp", "uk pmi", "uk manufacturing",
    ],
    "USDJPY": [
        "bank of japan", "boj", "yen", "usd/jpy", "japan gdp",
        "japan inflation", "japan pmi",
    ],
}


def _detect_tickers_by_keywords(
    title: str, body: str | None, all_tickers: list[Ticker]
) -> list[Ticker]:
    text = (title + " " + (body or "")).lower()
    enabled_symbols = {t.symbol for t in all_tickers}
    # Žádný fallback — zpráva bez keyword shody se sledovaným tickerem se ignoruje.
    # (Dřívější default na EURUSD posílal veškerý nezařazený šum do LLM predikcí.)
    return [
        t for t in all_tickers
        if t.symbol in KEYWORD_TICKER_MAP
        and any(kw in text for kw in KEYWORD_TICKER_MAP[t.symbol])
        and t.symbol in enabled_symbols
    ]


def _build_sources() -> list[NewsSource]:
    sources: list[NewsSource] = [
        ForexFactoryAdapter(),
        NewsAPIAdapter(),
        FinnhubAdapter(),
        AlphaVantageAdapter(),
    ]
    sources.extend(build_default_rss_adapters())
    return [s for s in sources if s.is_available() or not hasattr(s, "is_available")]


class NewsAggregator:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = NewsRepository(session)
        self.ticker_repo = TickerRepository(session)

    async def _fetch_all_sources(self) -> list[tuple[NewsSource, list[RawNewsItem]]]:
        sources = _build_sources()

        async def _safe_fetch(source: NewsSource) -> tuple[NewsSource, list[RawNewsItem]]:
            try:
                items = await asyncio.wait_for(source.fetch(), timeout=18.0)
                log.info("Source fetch OK", source=source.name, count=len(items))
                return source, items
            except asyncio.TimeoutError:
                log.warning("Source fetch timeout", source=source.name)
                return source, []
            except Exception as e:
                log.error("Source fetch error", source=source.name, error=str(e))
                return source, []

        results = await asyncio.gather(*[_safe_fetch(s) for s in sources])
        return list(results)

    async def _get_relevant_tickers(
        self,
        instruments_hint: list[str],
        all_tickers: Sequence[Ticker],
        title: str = "",
        body: str | None = None,
    ) -> list[Ticker]:
        if instruments_hint:
            return [t for t in all_tickers if t.symbol in instruments_hint]
        return _detect_tickers_by_keywords(title, body, list(all_tickers))

    async def refresh(self, max_predictions: int = 0) -> dict[str, int]:
        """Stáhne RSS a uloží nové položky do DB — BEZ LLM predikcí.

        Predikce jsou záměrně odděleny do predict_pending(), aby se refresh
        vešel do 60s Vercel limitu. Cron volá: refresh → predict → calibrate.
        """
        log.info("News aggregator refresh start (fetch-only)")
        source_results = await self._fetch_all_sources()
        enabled_tickers = list(await self.ticker_repo.get_all_enabled())

        stats = {"fetched": 0, "new": 0, "skipped": 0, "irrelevant": 0, "predicted": 0}

        for source, raw_items in source_results:
            if not raw_items:
                continue
            stats["fetched"] += len(raw_items)
            db_source = await self.repo.get_or_create_source(source.name)
            db_source.source_weight = source.source_weight

            # Batch lookup: 2 SQL dotazy místo N+1
            ext_ids = [r.external_id for r in raw_items]
            known = await self.repo.get_known_external_ids(db_source.id, ext_ids)
            predicted_ids = await self.repo.get_predicted_news_ids(list(known.values()))

            for raw in raw_items:
                if raw.external_id in known:
                    if known[raw.external_id] in predicted_ids:
                        stats["skipped"] += 1
                else:
                    # Filtr už při ingestu: zpráva bez vztahu ke sledovanému
                    # tickeru se vůbec neukládá (šetří DB i LLM cally)
                    hint = raw.instruments_hint or []
                    relevant = await self._get_relevant_tickers(
                        hint, enabled_tickers, raw.title, raw.body
                    )
                    if not relevant:
                        stats["irrelevant"] += 1
                        continue
                    await self.repo.create_news_item(
                        source_id=db_source.id,
                        external_id=raw.external_id,
                        title=raw.title,
                        body=raw.body,
                        url=raw.url,
                        published_at=raw.published_at,
                        raw_payload=raw.raw_payload,
                    )
                    stats["new"] += 1

            await self.session.commit()

        log.info("News aggregator refresh complete", **stats)
        return stats

    async def predict_pending(self, max_predictions: int = 8) -> dict[str, int]:
        """Spustí LLM predikce jen pro položky bez predikcí — bez RSS fetche."""
        log.info("Predict pending start", max_predictions=max_predictions)
        tickers = await self.ticker_repo.get_all_enabled()
        items = await self.repo.get_unpredicted_items(limit=max_predictions + 5)

        stats = {"pending": len(items), "predicted": 0, "errors": 0}
        engine = PredictionEngine(self.repo)

        stats["purged"] = 0
        for item in items:
            if stats["predicted"] >= max_predictions:
                break
            source_weight = item.source.source_weight if item.source else 0.5
            instruments_hint: list[str] = item.raw_payload.get("instruments_hint", []) if item.raw_payload else []
            relevant_tickers = await self._get_relevant_tickers(
                instruments_hint, tickers, item.title, item.body
            )
            if not relevant_tickers:
                # Položka bez vztahu ke sledovaným tickerům by frontu blokovala
                # navždy (nikdy nedostane predikci) — smaž ji
                await self.session.delete(item)
                stats["purged"] += 1
                continue
            for ticker in relevant_tickers:
                try:
                    result = await engine.predict(
                        news_id=item.id,
                        ticker_id=ticker.id,
                        ticker_symbol=ticker.symbol,
                        title=item.title,
                        body=item.body,
                        source_weight=source_weight,
                    )
                    await self.repo.upsert_ticker_relevance(
                        news_id=item.id,
                        ticker_id=ticker.id,
                        relevance_score=result.relevance_score,
                        importance_weight=result.importance_weight,
                        llm_rationale=result.llm_reasoning,
                    )
                    await self.repo.create_prediction(
                        news_id=item.id,
                        ticker_id=ticker.id,
                        prob_down=result.prob_down,
                        prob_neutral=result.prob_neutral,
                        prob_up=result.prob_up,
                        confidence=result.confidence,
                        llm_reasoning=result.llm_reasoning,
                        model_version=result.model_version,
                    )
                    await self.repo.save_item_categories(
                        item.id, [(cat, 1.0) for cat in result.categories]
                    )
                    stats["predicted"] += 1
                except Exception as e:
                    stats["errors"] += 1
                    log.error("Predict pending error", news_id=item.id, ticker=ticker.symbol, error=str(e))
            await self.session.commit()

        remaining = await self.repo.get_unpredicted_items(limit=1)
        stats["remaining"] = len(remaining)
        log.info("Predict pending complete", **stats)
        return stats
