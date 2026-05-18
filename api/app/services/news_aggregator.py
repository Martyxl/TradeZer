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

# Keywords mapped to ticker symbols — used when a source has no instruments_hint
KEYWORD_TICKER_MAP: dict[str, list[str]] = {
    "XAUUSD": [
        "gold", "xau", "bullion", "precious metal", "precious metals",
        "gold price", "gold futures", "gold market", "gold rally",
        "silver price", "silver futures", "commodity",
    ],
    "BTCUSD": ["bitcoin", "btc", "crypto", "cryptocurrency", "ethereum", "digital asset"],
    "ES":     ["s&p 500", "s&p500", "wall street", "dow jones", "nyse", "u.s. stocks", "us stocks"],
    "NQ":     ["nasdaq", "tech sector", "tech stocks", "big tech"],
    "EURUSD": [
        "european central bank", "ecb ", "eurozone", "euro area",
        "lagarde", "eur/usd", "euro/dollar",
    ],
}


def _detect_tickers_by_keywords(
    title: str, body: str | None, all_tickers: list[Ticker]
) -> list[Ticker]:
    text = (title + " " + (body or "")).lower()
    enabled_symbols = {t.symbol for t in all_tickers}
    matched = [
        t for t in all_tickers
        if t.symbol in KEYWORD_TICKER_MAP
        and any(kw in text for kw in KEYWORD_TICKER_MAP[t.symbol])
        and t.symbol in enabled_symbols
    ]
    # Fallback: default to EURUSD if no keyword match
    if not matched:
        matched = [t for t in all_tickers if t.symbol == "EURUSD"]
    return matched


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
        tasks = [(source, source.fetch()) for source in sources]
        results = []
        for source, coro in tasks:
            try:
                items = await coro
                results.append((source, items))
            except Exception as e:
                log.error("Source fetch error", source=source.name, error=str(e))
                results.append((source, []))
        return results

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

    async def refresh(self, max_predictions: int = 15) -> dict[str, int]:
        log.info("News aggregator refresh start", max_predictions=max_predictions)
        tickers = await self.ticker_repo.get_all_enabled()
        source_results = await self._fetch_all_sources()

        stats = {"fetched": 0, "new": 0, "skipped": 0, "predicted": 0}

        for source, raw_items in source_results:
            stats["fetched"] += len(raw_items)
            db_source = await self.repo.get_or_create_source(source.name)
            # Sync source weight to DB
            db_source.source_weight = source.source_weight

            for raw in raw_items:
                existing = await self.repo.get_news_item_by_external(
                    db_source.id, raw.external_id
                )
                if existing:
                    # Pokud položka existuje ale nemá predikce, přepočítej ji
                    has_pred = await self.repo.has_any_prediction(existing.id)
                    if has_pred:
                        stats["skipped"] += 1
                        continue
                    news_item = existing
                else:
                    news_item = await self.repo.create_news_item(
                        source_id=db_source.id,
                        external_id=raw.external_id,
                        title=raw.title,
                        body=raw.body,
                        url=raw.url,
                        published_at=raw.published_at,
                        raw_payload=raw.raw_payload,
                    )
                    stats["new"] += 1

                relevant_tickers = await self._get_relevant_tickers(
                    raw.instruments_hint, tickers, raw.title, raw.body
                )

                engine = PredictionEngine(self.repo)
                for ticker in relevant_tickers:
                    try:
                        result = await engine.predict(
                            news_id=news_item.id,
                            ticker_id=ticker.id,
                            ticker_symbol=ticker.symbol,
                            title=raw.title,
                            body=raw.body,
                            source_weight=source.source_weight,
                        )

                        await self.repo.upsert_ticker_relevance(
                            news_id=news_item.id,
                            ticker_id=ticker.id,
                            relevance_score=result.relevance_score,
                            importance_weight=result.importance_weight,
                            llm_rationale=result.llm_reasoning,
                        )
                        await self.repo.create_prediction(
                            news_id=news_item.id,
                            ticker_id=ticker.id,
                            prob_down=result.prob_down,
                            prob_neutral=result.prob_neutral,
                            prob_up=result.prob_up,
                            confidence=result.confidence,
                            llm_reasoning=result.llm_reasoning,
                            model_version=result.model_version,
                        )
                        await self.repo.save_item_categories(
                            news_item.id,
                            [(cat, 1.0) for cat in result.categories],
                        )
                        stats["predicted"] += 1
                    except Exception as e:
                        log.error(
                            "Prediction error",
                            news_id=news_item.id,
                            ticker=ticker.symbol,
                            error=str(e),
                        )

                # Commit po každé položce a zkontroluj limit
                await self.session.commit()
                if stats["predicted"] >= max_predictions:
                    log.info("Prediction batch limit reached", limit=max_predictions)
                    stats["fetched"] = -1  # signál že jsou ještě další
                    return stats

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

        for item in items:
            if stats["predicted"] >= max_predictions:
                break
            source_weight = item.source.source_weight if item.source else 0.5
            instruments_hint: list[str] = item.raw_payload.get("instruments_hint", []) if item.raw_payload else []
            relevant_tickers = await self._get_relevant_tickers(
                instruments_hint, tickers, item.title, item.body
            )
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
