"""Repository pro NewsItem a příbuzné modely."""
from datetime import datetime, date
from typing import Sequence

from sqlalchemy import select, and_, or_, func, not_, exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    NewsItem, NewsSource, NewsTicker, NewsPrediction,
    MarketReaction, NewsCategory, NewsItemCategory, DailySummary, Ticker
)


class NewsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create_source(self, name: str) -> NewsSource:
        src = await self.session.scalar(select(NewsSource).where(NewsSource.name == name))
        if not src:
            src = NewsSource(name=name)
            self.session.add(src)
            await self.session.flush()
        return src

    async def has_any_prediction(self, news_id: int) -> bool:
        result = await self.session.scalar(
            select(NewsPrediction).where(NewsPrediction.news_id == news_id).limit(1)
        )
        return result is not None

    async def get_unpredicted_items(self, limit: int = 20) -> Sequence[NewsItem]:
        """Vrátí news_items bez jakékoli predikce — pro dávkové zpracování."""
        stmt = (
            select(NewsItem)
            .where(
                not_(exists(
                    select(NewsPrediction.news_id)
                    .where(NewsPrediction.news_id == NewsItem.id)
                    .correlate(NewsItem)
                ))
            )
            .options(selectinload(NewsItem.source))
            .order_by(NewsItem.published_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_news_item_by_external(self, source_id: int, external_id: str) -> NewsItem | None:
        return await self.session.scalar(
            select(NewsItem).where(
                NewsItem.source_id == source_id,
                NewsItem.external_id == external_id,
            )
        )

    async def get_known_external_ids(self, source_id: int, external_ids: list[str]) -> dict[str, int]:
        """Batch lookup: {external_id → news_id} v jednom SQL dotazu."""
        if not external_ids:
            return {}
        rows = await self.session.execute(
            select(NewsItem.external_id, NewsItem.id).where(
                NewsItem.source_id == source_id,
                NewsItem.external_id.in_(external_ids),
            )
        )
        return {ext_id: news_id for ext_id, news_id in rows.all()}

    async def get_predicted_news_ids(self, news_ids: list[int]) -> set[int]:
        """Batch lookup: set news_id s aspoň 1 predikcí."""
        if not news_ids:
            return set()
        rows = await self.session.execute(
            select(NewsPrediction.news_id).where(NewsPrediction.news_id.in_(news_ids)).distinct()
        )
        return {row[0] for row in rows.all()}

    async def create_news_item(
        self,
        source_id: int,
        external_id: str,
        title: str,
        body: str | None,
        url: str,
        published_at: datetime,
        raw_payload: dict,
    ) -> NewsItem:
        item = NewsItem(
            source_id=source_id,
            external_id=external_id,
            title=title,
            body=body,
            url=url,
            published_at=published_at,
            raw_payload=raw_payload,
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def upsert_ticker_relevance(
        self,
        news_id: int,
        ticker_id: int,
        relevance_score: float,
        importance_weight: float,
        llm_rationale: str | None = None,
    ) -> NewsTicker:
        existing = await self.session.scalar(
            select(NewsTicker).where(
                NewsTicker.news_id == news_id,
                NewsTicker.ticker_id == ticker_id,
            )
        )
        if existing:
            existing.relevance_score = relevance_score
            existing.importance_weight = importance_weight
            existing.llm_rationale = llm_rationale
            return existing
        rel = NewsTicker(
            news_id=news_id,
            ticker_id=ticker_id,
            relevance_score=relevance_score,
            importance_weight=importance_weight,
            llm_rationale=llm_rationale,
        )
        self.session.add(rel)
        await self.session.flush()
        return rel

    async def create_prediction(
        self,
        news_id: int,
        ticker_id: int,
        prob_down: float,
        prob_neutral: float,
        prob_up: float,
        confidence: float,
        llm_reasoning: str | None,
        model_version: str,
    ) -> NewsPrediction:
        pred = NewsPrediction(
            news_id=news_id,
            ticker_id=ticker_id,
            prob_down=prob_down,
            prob_neutral=prob_neutral,
            prob_up=prob_up,
            confidence=confidence,
            llm_reasoning=llm_reasoning,
            model_version=model_version,
        )
        self.session.add(pred)
        await self.session.flush()
        return pred

    async def get_news_list(
        self,
        ticker_id: int,
        for_date: date | None = None,
        limit: int = 25,
        offset: int = 0,
    ) -> Sequence[NewsItem]:
        stmt = (
            select(NewsItem)
            .join(NewsTicker, NewsTicker.news_id == NewsItem.id)
            .where(NewsTicker.ticker_id == ticker_id)
            .options(
                selectinload(NewsItem.source),
                selectinload(NewsItem.predictions).selectinload(NewsPrediction.ticker),
                selectinload(NewsItem.ticker_relevances).selectinload(NewsTicker.ticker),
            )
            .order_by(NewsItem.published_at.desc())
        )
        if for_date:
            stmt = stmt.where(func.date(NewsItem.published_at) == for_date)
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_news_by_id(self, news_id: int) -> NewsItem | None:
        return await self.session.scalar(
            select(NewsItem)
            .where(NewsItem.id == news_id)
            .options(
                selectinload(NewsItem.source),
                selectinload(NewsItem.predictions),
                selectinload(NewsItem.ticker_relevances),
                selectinload(NewsItem.categories).selectinload(NewsItemCategory.category),
            )
        )

    async def get_predictions_without_reactions(
        self, older_than_minutes: int = 15
    ) -> Sequence[NewsPrediction]:
        """Predikce bez záznamu MarketReaction NEBO s reakcí ale null realized_direction."""
        import datetime as dt
        cutoff = datetime.utcnow() - dt.timedelta(minutes=older_than_minutes)
        stmt = (
            select(NewsPrediction)
            .outerjoin(
                MarketReaction,
                and_(
                    MarketReaction.news_id == NewsPrediction.news_id,
                    MarketReaction.ticker_id == NewsPrediction.ticker_id,
                ),
            )
            .where(
                or_(
                    MarketReaction.id.is_(None),
                    MarketReaction.realized_direction.is_(None),
                ),
                NewsPrediction.created_at <= cutoff,
            )
            .options(selectinload(NewsPrediction.news_item), selectinload(NewsPrediction.ticker))
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def save_market_reaction(
        self,
        news_id: int,
        ticker_id: int,
        price_at_news: float | None,
        price_15m: float | None,
        price_1h: float | None,
        price_1d: float | None,
        pct_change_15m: float | None,
        pct_change_1h: float | None,
        pct_change_1d: float | None,
        realized_direction: str | None,
        price_series: dict | None = None,
    ) -> MarketReaction:
        # Upsert — aktualizuj existující reakci nebo vytvoř novou
        existing = await self.session.scalar(
            select(MarketReaction).where(
                MarketReaction.news_id == news_id,
                MarketReaction.ticker_id == ticker_id,
            )
        )
        if existing:
            existing.price_at_news = price_at_news
            existing.price_15m = price_15m
            existing.price_1h = price_1h
            existing.price_1d = price_1d
            existing.pct_change_15m = pct_change_15m
            existing.pct_change_1h = pct_change_1h
            existing.pct_change_1d = pct_change_1d
            existing.price_series = price_series
            existing.realized_direction = realized_direction
            await self.session.flush()
            return existing
        reaction = MarketReaction(
            news_id=news_id,
            ticker_id=ticker_id,
            price_at_news=price_at_news,
            price_15m=price_15m,
            price_1h=price_1h,
            price_1d=price_1d,
            pct_change_15m=pct_change_15m,
            pct_change_1h=pct_change_1h,
            pct_change_1d=pct_change_1d,
            price_series=price_series,
            realized_direction=realized_direction,
        )
        self.session.add(reaction)
        await self.session.flush()
        return reaction

    async def get_reactions_missing_price_series(self, days: int = 7) -> list["MarketReaction"]:
        """Vrátí MarketReaction záznamy bez price_series dat (max. poslední `days` dní)."""
        from datetime import timedelta
        from sqlalchemy.orm import selectinload
        cutoff = datetime.utcnow() - timedelta(days=days)
        stmt = (
            select(MarketReaction)
            .join(NewsItem, NewsItem.id == MarketReaction.news_id)
            .where(
                MarketReaction.price_series.is_(None),
                MarketReaction.price_at_news.isnot(None),
                NewsItem.published_at >= cutoff,
            )
            .options(
                selectinload(MarketReaction.news_item),
                selectinload(MarketReaction.ticker),
            )
            .order_by(NewsItem.published_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_category_patterns(
        self,
        ticker_id: int,
        categories: list[str],
        days: int = 180,
        min_samples: int = 3,
    ) -> list[dict]:
        """Pro každou kategorii vrátí statistiky historického pohybu ceny (pattern memory)."""
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=days)

        results = []
        for cat_name in categories:
            stmt = (
                select(
                    MarketReaction.pct_change_15m,   # = 30min okno
                    MarketReaction.pct_change_1h,
                    MarketReaction.realized_direction,
                    MarketReaction.price_series,
                )
                .join(NewsItem, NewsItem.id == MarketReaction.news_id)
                .join(NewsItemCategory, NewsItemCategory.news_id == NewsItem.id)
                .join(NewsCategory, NewsCategory.id == NewsItemCategory.category_id)
                .where(
                    MarketReaction.ticker_id == ticker_id,
                    NewsCategory.name == cat_name,
                    MarketReaction.realized_direction.isnot(None),
                    MarketReaction.pct_change_15m.isnot(None),
                    NewsItem.published_at >= cutoff,
                )
            )
            rows = (await self.session.execute(stmt)).all()
            if len(rows) < min_samples:
                continue

            n = len(rows)
            pct30 = [r.pct_change_15m for r in rows]
            abs30 = sorted(abs(p) for p in pct30)

            dir_dist: dict[str, int] = {"up": 0, "neutral": 0, "down": 0}
            for r in rows:
                d = r.realized_direction if isinstance(r.realized_direction, str) else r.realized_direction.value
                dir_dist[d] = dir_dist.get(d, 0) + 1

            # price_series stats (dostupné až u novějších dat)
            ps_rows = [r.price_series for r in rows if r.price_series]
            grabs = [ps.get("liquidity_grab", False) for ps in ps_rows]
            grab_rate = sum(grabs) / len(grabs) if grabs else 0.0

            spikes_5m = [abs(ps.get("pct_5m") or 0) for ps in ps_rows if ps.get("pct_5m") is not None]

            # Typický scénář: popis vzoru
            dominant_dir = max(dir_dist, key=lambda k: dir_dist[k])
            dominant_pct = round(dir_dist[dominant_dir] / n * 100)

            results.append({
                "category": cat_name,
                "sample_count": n,
                "direction_distribution": dir_dist,
                "dominant_direction": dominant_dir,
                "dominant_pct": dominant_pct,
                "avg_abs_move_30m_pct": round(sum(abs30) / n * 100, 4),
                "p50_abs_move_30m_pct": round(abs30[n // 2] * 100, 4),
                "p75_abs_move_30m_pct": round(abs30[int(n * 0.75)] * 100, 4),
                "avg_pct_1h": round(
                    sum(r.pct_change_1h or 0 for r in rows) / n * 100, 4
                ),
                "liquidity_grab_rate": round(grab_rate, 3),
                "liquidity_grab_samples": len(grabs),
                "avg_initial_spike_5m_pct": (
                    round(sum(spikes_5m) / len(spikes_5m) * 100, 4) if spikes_5m else None
                ),
            })

        return sorted(results, key=lambda x: -x["sample_count"])

    async def get_historical_direction_by_category(
        self, category_name: str, ticker_id: int
    ) -> dict[str, int]:
        stmt = (
            select(
                MarketReaction.realized_direction,
                func.count(MarketReaction.id).label("cnt"),
            )
            .join(NewsItem, NewsItem.id == MarketReaction.news_id)
            .join(NewsItemCategory, NewsItemCategory.news_id == NewsItem.id)
            .join(NewsCategory, NewsCategory.id == NewsItemCategory.category_id)
            .where(
                NewsCategory.name == category_name,
                MarketReaction.ticker_id == ticker_id,
                MarketReaction.realized_direction.isnot(None),
            )
            .group_by(MarketReaction.realized_direction)
        )
        result = await self.session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def get_or_create_category(self, name: str) -> NewsCategory:
        cat = await self.session.scalar(select(NewsCategory).where(NewsCategory.name == name))
        if not cat:
            cat = NewsCategory(name=name)
            self.session.add(cat)
            await self.session.flush()
        return cat

    async def save_item_categories(
        self, news_id: int, categories: list[tuple[str, float]]
    ) -> None:
        for cat_name, confidence in categories:
            cat = await self.get_or_create_category(cat_name)
            existing = await self.session.scalar(
                select(NewsItemCategory).where(
                    NewsItemCategory.news_id == news_id,
                    NewsItemCategory.category_id == cat.id,
                )
            )
            if not existing:
                self.session.add(NewsItemCategory(
                    news_id=news_id, category_id=cat.id, confidence=confidence
                ))

    async def upsert_daily_summary(
        self,
        ticker_id: int,
        for_date: date,
        prob_down: float,
        prob_neutral: float,
        prob_up: float,
        recommendation: str,
        top_drivers: dict,
    ) -> DailySummary:
        existing = await self.session.scalar(
            select(DailySummary).where(
                DailySummary.ticker_id == ticker_id,
                DailySummary.date == for_date,
            )
        )
        if existing:
            existing.overall_prob_down = prob_down
            existing.overall_prob_neutral = prob_neutral
            existing.overall_prob_up = prob_up
            existing.recommendation = recommendation
            existing.top_drivers = top_drivers
            return existing
        summary = DailySummary(
            ticker_id=ticker_id,
            date=for_date,
            overall_prob_down=prob_down,
            overall_prob_neutral=prob_neutral,
            overall_prob_up=prob_up,
            recommendation=recommendation,
            top_drivers=top_drivers,
        )
        self.session.add(summary)
        await self.session.flush()
        return summary

    async def get_high_impact_events(self, for_date: date | None = None) -> Sequence[NewsItem]:
        from datetime import date as _date
        today = for_date or _date.today()
        HIGH = {
            "monetary_policy", "inflation", "employment", "pmi",
            "central_bank_minutes", "gdp", "surprise_beat", "surprise_miss",
            "ecb_speech", "fed_speech",
        }
        stmt = (
            select(NewsItem)
            .join(NewsItemCategory, NewsItemCategory.news_id == NewsItem.id)
            .join(NewsCategory, NewsCategory.id == NewsItemCategory.category_id)
            .where(
                NewsCategory.name.in_(HIGH),
                func.date(NewsItem.published_at) == today,
            )
            .options(
                selectinload(NewsItem.categories).selectinload(NewsItemCategory.category),
                selectinload(NewsItem.ticker_relevances),
            )
            .distinct()
            .order_by(NewsItem.published_at)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_daily_summary(self, ticker_id: int, for_date: date) -> DailySummary | None:
        return await self.session.scalar(
            select(DailySummary).where(
                DailySummary.ticker_id == ticker_id,
                DailySummary.date == for_date,
            )
        )

    async def get_accuracy_stats(
        self, ticker_id: int, days: int = 90
    ) -> dict:
        """Celková přesnost + per-kategorie za posledních N dní."""
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=days)

        # Celkové počty: kolik predikcí má realizovanou reakci
        total_stmt = (
            select(func.count(MarketReaction.id))
            .join(NewsPrediction, and_(
                NewsPrediction.news_id == MarketReaction.news_id,
                NewsPrediction.ticker_id == MarketReaction.ticker_id,
            ))
            .where(
                MarketReaction.ticker_id == ticker_id,
                MarketReaction.realized_direction.isnot(None),
                MarketReaction.recorded_at >= cutoff,
            )
        )
        total = (await self.session.scalar(total_stmt)) or 0

        # Přesné: predikovaný směr == realizovaný
        # Predikovaný směr = argmax(prob_down, prob_neutral, prob_up)
        # Počítáme v Pythonu — stáhneme řádky
        rows_stmt = (
            select(
                NewsPrediction.prob_down,
                NewsPrediction.prob_neutral,
                NewsPrediction.prob_up,
                MarketReaction.realized_direction,
            )
            .join(NewsPrediction, and_(
                NewsPrediction.news_id == MarketReaction.news_id,
                NewsPrediction.ticker_id == MarketReaction.ticker_id,
            ))
            .where(
                MarketReaction.ticker_id == ticker_id,
                MarketReaction.realized_direction.isnot(None),
                MarketReaction.recorded_at >= cutoff,
            )
        )
        rows = (await self.session.execute(rows_stmt)).all()

        correct = sum(
            1 for r in rows
            if max(
                ("down", r.prob_down), ("neutral", r.prob_neutral), ("up", r.prob_up),
                key=lambda x: x[1]
            )[0] == (r.realized_direction if isinstance(r.realized_direction, str) else r.realized_direction.value)
        )

        # Per-kategorie
        cat_stmt = (
            select(
                NewsCategory.name,
                MarketReaction.realized_direction,
                NewsPrediction.prob_down,
                NewsPrediction.prob_neutral,
                NewsPrediction.prob_up,
            )
            .join(NewsPrediction, and_(
                NewsPrediction.news_id == MarketReaction.news_id,
                NewsPrediction.ticker_id == MarketReaction.ticker_id,
            ))
            .join(NewsItemCategory, NewsItemCategory.news_id == MarketReaction.news_id)
            .join(NewsCategory, NewsCategory.id == NewsItemCategory.category_id)
            .where(
                MarketReaction.ticker_id == ticker_id,
                MarketReaction.realized_direction.isnot(None),
                MarketReaction.recorded_at >= cutoff,
            )
        )
        cat_rows = (await self.session.execute(cat_stmt)).all()

        by_cat: dict[str, dict] = {}
        for r in cat_rows:
            cat = r.name
            realized = r.realized_direction if isinstance(r.realized_direction, str) else r.realized_direction.value
            predicted = max(
                ("down", r.prob_down), ("neutral", r.prob_neutral), ("up", r.prob_up),
                key=lambda x: x[1]
            )[0]
            if cat not in by_cat:
                by_cat[cat] = {"total": 0, "correct": 0, "up": 0, "neutral": 0, "down": 0}
            by_cat[cat]["total"] += 1
            by_cat[cat][realized] += 1
            if predicted == realized:
                by_cat[cat]["correct"] += 1

        return {
            "total": total,
            "correct": correct,
            "accuracy": round(correct / total, 4) if total > 0 else None,
            "by_category": {
                cat: {
                    **v,
                    "accuracy": round(v["correct"] / v["total"], 4) if v["total"] > 0 else None,
                }
                for cat, v in sorted(by_cat.items(), key=lambda x: -x[1]["total"])
            },
        }
