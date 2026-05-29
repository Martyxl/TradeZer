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
