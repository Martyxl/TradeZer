import os

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.schemas import RefreshResponse
from app.services.news_aggregator import NewsAggregator

router = APIRouter(prefix="/api", tags=["admin"])


def _verify_token(
    x_internal_token: str = Header(default=""),
    authorization: str = Header(default=""),
):
    # Accept X-Internal-Token (manual calls, cron-job.org)
    if settings.internal_api_token and x_internal_token == settings.internal_api_token:
        return
    # Accept Vercel cron: Authorization: Bearer <CRON_SECRET>
    cron_secret = os.environ.get("CRON_SECRET", "")
    if cron_secret and authorization == f"Bearer {cron_secret}":
        return
    # Reject if token is configured but nothing matched
    if settings.internal_api_token:
        raise HTTPException(status_code=401, detail="Neplatný token")


@router.post("/refresh", response_model=RefreshResponse, dependencies=[Depends(_verify_token)])
async def manual_refresh(
    session: AsyncSession = Depends(get_session),
):
    """Stáhne RSS a uloží nové zprávy. Predikce jsou v /api/predict."""
    aggregator = NewsAggregator(session)
    stats = await aggregator.refresh()
    return RefreshResponse(status="ok", stats=stats)


# Timestamp posledního veřejného refreshe — základní rate limit (60s)
_last_public_refresh: float = 0.0


@router.post("/public/refresh")
async def public_refresh(
    session: AsyncSession = Depends(get_session),
):
    """Veřejný endpoint pro manuální refresh z UI — nevyžaduje token.

    Stáhne nové zprávy ze všech zdrojů a spustí LLM predikce.
    Rate limit: max jednou za 60 sekund.
    """
    import time
    global _last_public_refresh
    now = time.time()
    cooldown = 60.0
    wait = cooldown - (now - _last_public_refresh)
    if wait > 0:
        return {
            "status": "rate_limited",
            "retry_after_seconds": round(wait),
            "message": f"Počkej ještě {round(wait)}s před dalším refreshem.",
        }
    _last_public_refresh = now

    aggregator = NewsAggregator(session)
    refresh_stats = await aggregator.refresh()
    predict_stats = await aggregator.predict_pending(max_predictions=8)
    return {
        "status": "ok",
        "new_items": refresh_stats.get("new", 0),
        "predicted": predict_stats.get("predicted", 0),
        "remaining": predict_stats.get("remaining", 0),
    }


@router.post("/predict", dependencies=[Depends(_verify_token)])
async def predict_pending(
    session: AsyncSession = Depends(get_session),
    max_predictions: int = Query(default=8, ge=1, le=30),
):
    """Spustí LLM predikce pro položky bez predikcí (bez RSS fetche — rychlejší)."""
    aggregator = NewsAggregator(session)
    stats = await aggregator.predict_pending(max_predictions=max_predictions)
    return {"status": "ok", "stats": stats}


@router.post("/calibrate", dependencies=[Depends(_verify_token)])
async def calibrate(
    session: AsyncSession = Depends(get_session),
):
    """Stáhne tržní ceny a zaznamená market reactions pro predikce starší 15 min."""
    from app.services.calibration_service import CalibrationService
    service = CalibrationService(session)
    stats = await service.run()
    return {"status": "ok", "stats": stats}


@router.get("/reactions/analysis", dependencies=[Depends(_verify_token)])
async def reactions_analysis(
    ticker: str = Query(default="EURUSD"),
    days: int = Query(default=90),
    session: AsyncSession = Depends(get_session),
):
    """Vrátí distribuci pct_change_15m pro daný ticker — pro kalibraci neutral_threshold."""
    from sqlalchemy import select, func as sqlfunc
    from app.models import MarketReaction, NewsItem
    from app.repositories import TickerRepository
    from datetime import datetime, timedelta

    ticker_repo = TickerRepository(session)
    ticker_obj = await ticker_repo.get_by_symbol(ticker)
    if not ticker_obj:
        return {"error": "ticker not found"}

    cutoff = datetime.utcnow() - timedelta(days=days)
    stmt = (
        select(MarketReaction.pct_change_15m, MarketReaction.realized_direction)
        .join(NewsItem, NewsItem.id == MarketReaction.news_id)
        .where(
            MarketReaction.ticker_id == ticker_obj.id,
            MarketReaction.pct_change_15m.isnot(None),
            NewsItem.published_at >= cutoff,
        )
        .order_by(MarketReaction.pct_change_15m)
    )
    result = await session.execute(stmt)
    rows = result.all()

    if not rows:
        return {"ticker": ticker, "count": 0, "message": "no data"}

    pcts = [abs(r.pct_change_15m) * 100 for r in rows]  # abs, v procentech
    raw_pcts = [round(r.pct_change_15m * 100, 4) for r in rows]

    pcts.sort()
    n = len(pcts)
    percentiles = {
        "p10": round(pcts[int(n * 0.10)], 4),
        "p25": round(pcts[int(n * 0.25)], 4),
        "p50": round(pcts[n // 2], 4),
        "p75": round(pcts[int(n * 0.75)], 4),
        "p90": round(pcts[int(n * 0.90)], 4),
        "p95": round(pcts[int(n * 0.95)], 4),
        "p99": round(pcts[min(int(n * 0.99), n - 1)], 4),
    }
    avg = round(sum(pcts) / n, 4)
    current_threshold = round(ticker_obj.neutral_threshold * 100, 4)

    # Kolik vzorků by bylo classified jako non-neutral při různých thresholdech
    thresholds_test = [0.01, 0.02, 0.03, 0.04, 0.05, 0.07, 0.10, 0.15, 0.20]
    threshold_sim = {
        f"{t*100:.0f}bp": {
            "non_neutral_count": sum(1 for p in pcts if p > t * 100),
            "non_neutral_pct": round(sum(1 for p in pcts if p > t * 100) / n * 100, 1),
        }
        for t in thresholds_test
    }

    return {
        "ticker": ticker,
        "current_threshold_pct": current_threshold,
        "count": n,
        "abs_pct_change_15m": {
            "avg": avg,
            "min": round(pcts[0], 4),
            "max": round(pcts[-1], 4),
            **percentiles,
        },
        "raw_sample_20": raw_pcts[:20],
        "threshold_simulation": threshold_sim,
    }


@router.patch("/tickers/{symbol}/threshold", dependencies=[Depends(_verify_token)])
async def update_threshold(
    symbol: str,
    threshold: float = Query(description="Nový neutral_threshold jako frakce (0.0005 = 0.05%)"),
    session: AsyncSession = Depends(get_session),
):
    """Aktualizuje neutral_threshold pro ticker. Po změně spusť /api/calibrate znovu."""
    from app.repositories import TickerRepository

    repo = TickerRepository(session)
    ticker = await repo.get_by_symbol(symbol.upper())
    if not ticker:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Ticker {symbol} not found")

    from sqlalchemy import update
    from app.models import MarketReaction

    from sqlalchemy import select as sa_select
    from app.models import MarketReaction, DirectionEnum

    old = ticker.neutral_threshold
    ticker.neutral_threshold = threshold

    # Přepočítej realized_direction přímo ze stored pct_change_15m
    mr_stmt = sa_select(MarketReaction).where(
        MarketReaction.ticker_id == ticker.id,
        MarketReaction.pct_change_15m.isnot(None),
    )
    mr_result = await session.execute(mr_stmt)
    reactions = mr_result.scalars().all()

    updated = skipped = 0
    for r in reactions:
        p = r.pct_change_15m
        if p > threshold:
            new_dir = DirectionEnum.UP
        elif p < -threshold:
            new_dir = DirectionEnum.DOWN
        else:
            new_dir = DirectionEnum.NEUTRAL
        r.realized_direction = new_dir
        updated += 1

    await session.commit()
    return {
        "symbol": symbol.upper(),
        "old_threshold": old,
        "new_threshold": threshold,
        "old_pct": round(old * 100, 4),
        "new_pct": round(threshold * 100, 4),
        "reactions_updated": updated,
        "message": "Threshold + realized_direction přepočítány ze stored pct_change_15m",
    }


@router.post("/repredict/reroute", dependencies=[Depends(_verify_token)])
async def reroute_predictions(
    days: int = Query(default=3, ge=1, le=14, description="Kolik dní zpět prohledat"),
    dry_run: bool = Query(default=False, description="True = jen zobraz co by se zpracovalo"),
    session: AsyncSession = Depends(get_session),
):
    """Doplní predikce pro tickery, které chybí u existujících zpráv.

    Problém: zprávy jako 'ISM Manufacturing' šly do EURUSD místo ES/NQ
    kvůli chybějícím keywords v mapě. Tento endpoint tyto zprávy znovu
    projde a přidá predikce pro správné tickery.

    Používá updated KEYWORD_TICKER_MAP a instruments_hint z raw_payload.
    """
    from datetime import timedelta
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models import NewsItem, NewsSource, NewsPrediction, NewsTicker
    from app.repositories import TickerRepository, NewsRepository
    from app.services.prediction_engine import PredictionEngine
    from app.services.news_aggregator import _detect_tickers_by_keywords

    ticker_repo = TickerRepository(session)
    news_repo = NewsRepository(session)
    all_tickers = await ticker_repo.get_all_enabled()
    engine = PredictionEngine(news_repo)

    cutoff = __import__("datetime").datetime.utcnow() - timedelta(days=days)

    # Všechny zprávy z posledních N dní s jejich predikcemi
    stmt = (
        select(NewsItem)
        .where(NewsItem.published_at >= cutoff)
        .options(
            selectinload(NewsItem.source),
            selectinload(NewsItem.predictions),
            selectinload(NewsItem.ticker_relevances),
        )
        .order_by(NewsItem.published_at.desc())
    )
    items = (await session.execute(stmt)).scalars().all()

    stats = {"checked": 0, "added": 0, "skipped": 0, "errors": 0}
    added_details = []

    for item in items:
        stats["checked"] += 1
        instruments_hint = item.raw_payload.get("instruments_hint", []) if item.raw_payload else []
        relevant_tickers = (
            [t for t in all_tickers if t.symbol in instruments_hint]
            if instruments_hint
            else _detect_tickers_by_keywords(item.title, item.body, list(all_tickers))
        )

        predicted_ticker_ids = {p.ticker_id for p in item.predictions}
        missing_tickers = [t for t in relevant_tickers if t.id not in predicted_ticker_ids]

        if not missing_tickers:
            stats["skipped"] += 1
            continue

        for ticker in missing_tickers:
            if dry_run:
                added_details.append({
                    "news_id": item.id,
                    "title": item.title[:80],
                    "ticker": ticker.symbol,
                    "published_at": str(item.published_at)[:16],
                })
                stats["added"] += 1
                continue

            try:
                source_weight = item.source.source_weight if item.source else 0.5
                result = await engine.predict(
                    news_id=item.id,
                    ticker_id=ticker.id,
                    ticker_symbol=ticker.symbol,
                    title=item.title,
                    body=item.body,
                    source_weight=source_weight,
                )
                await news_repo.upsert_ticker_relevance(
                    news_id=item.id,
                    ticker_id=ticker.id,
                    relevance_score=result.relevance_score,
                    importance_weight=result.importance_weight,
                    llm_rationale=result.llm_reasoning,
                )
                await news_repo.create_prediction(
                    news_id=item.id,
                    ticker_id=ticker.id,
                    prob_down=result.prob_down,
                    prob_neutral=result.prob_neutral,
                    prob_up=result.prob_up,
                    confidence=result.confidence,
                    llm_reasoning=result.llm_reasoning,
                    model_version=result.model_version,
                )
                await news_repo.save_item_categories(
                    item.id, [(cat, 1.0) for cat in result.categories]
                )
                added_details.append({
                    "news_id": item.id,
                    "title": item.title[:80],
                    "ticker": ticker.symbol,
                    "direction": max(
                        [("up", result.prob_up), ("neutral", result.prob_neutral), ("down", result.prob_down)],
                        key=lambda x: x[1]
                    )[0],
                    "published_at": str(item.published_at)[:16],
                })
                stats["added"] += 1
            except Exception as e:
                stats["errors"] += 1

        if not dry_run:
            await session.commit()

    return {
        "status": "ok",
        "dry_run": dry_run,
        "stats": stats,
        "added": added_details[:50],  # max 50 details
    }


@router.post("/repredict/fix-defaults", dependencies=[Depends(_verify_token)])
async def fix_default_predictions(
    days: int = Query(default=7, ge=1, le=30),
    max_items: int = Query(default=20, ge=1, le=100),
    dry_run: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
):
    """Přepíše predikce s confidence=0.0 (defaultní hodnoty) přes LLM.

    Tyto predikce vznikly když predict job nedoběhl nebo selhal — uložily
    se rovnoměrné pravděpodobnosti 0.333/0.333/0.333 bez LLM výpočtu.
    """
    from datetime import timedelta
    from sqlalchemy import select, update
    from sqlalchemy.orm import selectinload
    from app.models import NewsItem, NewsPrediction
    from app.repositories import TickerRepository, NewsRepository
    from app.services.prediction_engine import PredictionEngine

    news_repo = NewsRepository(session)
    ticker_repo = TickerRepository(session)
    all_tickers = await ticker_repo.get_all_enabled()
    engine = PredictionEngine(news_repo)

    cutoff = __import__("datetime").datetime.utcnow() - timedelta(days=days)

    # Najdi predikce s confidence=0 z posledních N dní
    stmt = (
        select(NewsPrediction)
        .join(NewsItem, NewsItem.id == NewsPrediction.news_id)
        .where(NewsPrediction.confidence == 0.0)
        .where(NewsItem.published_at >= cutoff)
        .options(selectinload(NewsPrediction.news_item).selectinload(NewsItem.source))
        .order_by(NewsItem.published_at.desc())
        .limit(max_items)
    )
    default_preds = (await session.execute(stmt)).scalars().all()

    stats = {"found": len(default_preds), "fixed": 0, "errors": 0}
    fixed_details = []

    for pred in default_preds:
        item = pred.news_item
        ticker = next((t for t in all_tickers if t.id == pred.ticker_id), None)
        if not ticker:
            continue

        if dry_run:
            fixed_details.append({"news_id": item.id, "title": item.title[:80], "ticker": ticker.symbol})
            stats["fixed"] += 1
            continue

        try:
            source_weight = item.source.source_weight if item.source else 0.5
            result = await engine.predict(
                news_id=item.id,
                ticker_id=ticker.id,
                ticker_symbol=ticker.symbol,
                title=item.title,
                body=item.body,
                source_weight=source_weight,
            )
            # Update predikci na místě
            await session.execute(
                update(NewsPrediction)
                .where(NewsPrediction.id == pred.id)
                .values(
                    prob_down=result.prob_down,
                    prob_neutral=result.prob_neutral,
                    prob_up=result.prob_up,
                    confidence=result.confidence,
                    llm_reasoning=result.llm_reasoning,
                    model_version=result.model_version,
                )
            )
            await news_repo.upsert_ticker_relevance(
                news_id=item.id,
                ticker_id=ticker.id,
                relevance_score=result.relevance_score,
                importance_weight=result.importance_weight,
                llm_rationale=result.llm_reasoning,
            )
            await news_repo.save_item_categories(item.id, [(cat, 1.0) for cat in result.categories])
            fixed_details.append({
                "news_id": item.id,
                "title": item.title[:80],
                "ticker": ticker.symbol,
                "direction": max(
                    [("up", result.prob_up), ("neutral", result.prob_neutral), ("down", result.prob_down)],
                    key=lambda x: x[1],
                )[0],
                "confidence": round(result.confidence, 2),
            })
            stats["fixed"] += 1
        except Exception as e:
            stats["errors"] += 1

    if not dry_run:
        await session.commit()

    return {"status": "ok", "dry_run": dry_run, "stats": stats, "fixed": fixed_details[:50]}


@router.post("/backfill/price_series", dependencies=[Depends(_verify_token)])
async def backfill_price_series(
    days: int = Query(default=7, ge=1, le=7, description="Max. 7 dní (limit Yahoo Finance 5min dat)"),
    session: AsyncSession = Depends(get_session),
):
    """Doplní price_series (5m/10m/liquidity_grab) do starých MarketReaction bez těchto dat.

    Volej jednorázově po nasazení pattern memory feature.
    Yahoo Finance 5min bary jsou dostupné max. 7 dní zpět.
    """
    from app.services.calibration_service import CalibrationService
    service = CalibrationService(session)
    stats = await service.backfill_price_series(days=days)
    return {"status": "ok", "stats": stats}


@router.get("/patterns/{ticker}", dependencies=[Depends(_verify_token)])
async def get_ticker_patterns(
    ticker: str,
    days: int = Query(default=180, description="Kolik dní historie"),
    category: str | None = Query(default=None, description="Filtr na konkrétní kategorii"),
    min_samples: int = Query(default=3, description="Minimální počet vzorků pro kategorii"),
    session: AsyncSession = Depends(get_session),
):
    """Historické vzory pohybu trhu po zprávách daného tickeru — pattern memory.

    Výstup slouží k přípravě na nadcházející zprávy: typický pohyb, reversal rate,
    liquidity grab frekvence.
    """
    from app.repositories import TickerRepository, NewsRepository

    ticker_repo = TickerRepository(session)
    ticker_obj = await ticker_repo.get_by_symbol(ticker.upper())
    if not ticker_obj:
        raise HTTPException(status_code=404, detail=f"Ticker {ticker} not found")

    repo = NewsRepository(session)

    ALL_CATEGORIES = [
        "monetary_policy", "inflation", "employment", "gdp", "pmi",
        "fed_speech", "ecb_speech", "geopolitical", "trade_balance",
        "central_bank_minutes", "retail_sales", "housing", "consumer_confidence",
        "energy", "earnings", "risk_sentiment", "fiscal_policy",
        "surprise_beat", "surprise_miss", "safe_haven", "equity_index", "tech_sector",
    ]
    categories = [category] if category else ALL_CATEGORIES

    patterns = await repo.get_category_patterns(
        ticker_obj.id, categories, days=days, min_samples=min_samples
    )

    return {
        "ticker": ticker.upper(),
        "days": days,
        "pattern_count": len(patterns),
        "patterns": patterns,
        "note": (
            "liquidity_grab_rate = podíl událostí kde cena nejdříve šla opačně než finální směr. "
            "p75_abs_move_30m_pct = 75th percentil absolutního pohybu za 30min (v %)."
        ),
    }


@router.get("/debug/bars", dependencies=[Depends(_verify_token)])
async def debug_bars(
    ticker: str = Query(default="ES", description="Ticker symbol (ES, NQ, EURUSD, XAUUSD...)"),
    date_str: str = Query(default="", description="YYYY-MM-DD (default: yesterday UTC)"),
):
    """Vrátí 5min bary pro daný ticker a den — pro kalibraci 30min reakce (NY open = 13:30-20:00 UTC)."""
    import asyncio
    import datetime as dt
    from app.sources.yahoo_finance_adapter import YahooFinanceAdapter, _find_close_at

    yahoo = YahooFinanceAdapter()

    if date_str:
        for_date = dt.date.fromisoformat(date_str)
    else:
        for_date = (dt.datetime.utcnow() - dt.timedelta(days=1)).date()

    bars = await asyncio.to_thread(yahoo.fetch_day_bars, ticker.upper(), for_date)
    if not bars:
        return {"ticker": ticker, "date": str(for_date), "error": "No bars returned from Yahoo Finance"}

    # Referenční cena: první bar dne
    open_price = bars[0]["close"]

    # NY open session window: 13:30–20:00 UTC (zahrnuje NY open + afternoon session)
    ny_open_ts = dt.datetime(for_date.year, for_date.month, for_date.day, 13, 30, tzinfo=dt.timezone.utc).timestamp()
    ny_close_ts = dt.datetime(for_date.year, for_date.month, for_date.day, 20, 0, tzinfo=dt.timezone.utc).timestamp()

    ny_bars = []
    for b in bars:
        if ny_open_ts <= b["t"] <= ny_close_ts:
            t = dt.datetime.fromtimestamp(b["t"], tz=dt.timezone.utc)
            pct = round((b["close"] - open_price) / open_price * 100, 4) if open_price else None
            ny_bars.append({
                "time_utc": t.strftime("%H:%M"),
                "close": round(b["close"], 4),
                "pct_from_open": pct,
            })

    # Checkpointy: +15, +30, +60 min od NY open
    ny_open_dt = dt.datetime(for_date.year, for_date.month, for_date.day, 13, 30, tzinfo=dt.timezone.utc)
    price_at_open = _find_close_at(bars, ny_open_dt)
    price_15m = _find_close_at(bars, ny_open_dt + dt.timedelta(minutes=15))
    price_30m = _find_close_at(bars, ny_open_dt + dt.timedelta(minutes=30))
    price_60m = _find_close_at(bars, ny_open_dt + dt.timedelta(hours=1))

    def pct(p):
        if p and price_at_open:
            return round((p - price_at_open) / price_at_open * 100, 4)
        return None

    return {
        "ticker": ticker.upper(),
        "date": str(for_date),
        "total_bars": len(bars),
        "ny_session_bars": len(ny_bars),
        "from_ny_open": {
            "price_at_open": price_at_open,
            "+15min": {"price": price_15m, "pct": pct(price_15m)},
            "+30min": {"price": price_30m, "pct": pct(price_30m)},
            "+60min": {"price": price_60m, "pct": pct(price_60m)},
        },
        "bars": ny_bars,
    }


@router.get("/health")
async def health():
    return {"status": "ok", "version": "1.1.0"}
