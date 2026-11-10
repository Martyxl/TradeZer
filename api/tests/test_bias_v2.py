"""Bias v2 (stínový): ověřené kategorie jen z minulosti, signál up−down, doplnění zpětně;
vyhodnocení starých dní z hodinových barů; historická úspěšnost s intervalem místo trust score."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models import DailyBias, NewsItem, NewsPrediction, Ticker
from app.models.news import DirectionEnum, MarketReaction, NewsCategory, NewsItemCategory, NewsSource
from app.services import bias_service as bs


def test_verified_categories_uses_only_the_past():
    t0 = datetime(2026, 10, 1)
    hits = sorted(
        [(t0 + timedelta(hours=i), "earnings", i % 10 < 8) for i in range(40)]          # 80 % z 40
        + [(t0 + timedelta(hours=i), "pmi", i % 2 == 0) for i in range(60)]              # 50 % → ne
        + [(t0 + timedelta(days=30, hours=i), "fed_speech", True) for i in range(40)],   # až později
        key=lambda x: x[0])
    assert bs.verified_categories(hits, t0 + timedelta(days=5)) == {"earnings"}
    # fed_speech je prokazatelně dobrá, ale až po daném dni → nesmí se použít (bez lookahead)
    assert bs.verified_categories(hits, t0 + timedelta(days=29)) == {"earnings"}
    assert bs.verified_categories(hits, t0 + timedelta(days=40)) == {"earnings", "fed_speech"}
    assert bs.verified_categories(hits[:20], t0 + timedelta(days=40)) == set()            # < 30 tipů


def test_v2_signal_sign_and_weights():
    assert bs.v2_signal([]) == {"direction": "none", "score": None, "n": 0}
    r = bs.v2_signal([(0.6, 0.2, 0.9), (0.2, 0.5, 0.1)])
    assert r["direction"] == "up" and r["n"] == 2 and r["score"] == pytest.approx((0.9 * 0.4 + 0.1 * -0.3) / 1.0, abs=1e-4)
    assert bs.v2_signal([(0.2, 0.6, 0.5)])["direction"] == "down"


async def _setup(db):
    src = NewsSource(name="test")
    t = Ticker(symbol="NQ", name="NQ", asset_class="futures", source_symbol_map={}, neutral_threshold=0.001)
    cats = {n: NewsCategory(name=n) for n in ("earnings", "pmi")}
    db.add_all([src, t, *cats.values()])
    await db.commit()
    return src, t, cats


async def _news(db, src, t, cat, when, up, down, realized=None, conf=0.8):
    n = NewsItem(source_id=src.id, external_id=f"{cat.name}{when.isoformat()}{up}", title="x", url="u", published_at=when)
    db.add(n)
    await db.flush()
    db.add(NewsItemCategory(news_id=n.id, category_id=cat.id))
    db.add(NewsPrediction(news_id=n.id, ticker_id=t.id, prob_up=up, prob_down=down, prob_neutral=1 - up - down,
                          confidence=conf))
    if realized:
        db.add(MarketReaction(news_id=n.id, ticker_id=t.id, realized_direction=realized))


@pytest.mark.asyncio
async def test_fill_v2_uses_verified_categories_only(db_session):
    db = db_session
    src, t, cats = await _setup(db)
    day = date(2026, 10, 14)                                   # středa
    hist = datetime(2026, 9, 1, 12)
    for i in range(40):                                        # earnings: tipy nahoru trefují 85 %
        await _news(db, src, t, cats["earnings"], hist + timedelta(hours=i), .6, .2,
                    DirectionEnum.UP if i % 20 < 17 else DirectionEnum.DOWN)
        await _news(db, src, t, cats["pmi"], hist + timedelta(hours=i), .6, .2,      # pmi: 50 %
                    DirectionEnum.UP if i % 2 else DirectionEnum.DOWN)
    # Ráno dne: earnings zpráva tipuje dolů, silná pmi zpráva nahoru (pmi se ignoruje)
    morning = datetime(2026, 10, 14, 5, 0)
    await _news(db, src, t, cats["earnings"], morning, .1, .6)
    await _news(db, src, t, cats["pmi"], morning, .9, .05, conf=1.0)
    await _news(db, src, t, cats["earnings"], datetime(2026, 10, 14, 10, 0), .9, .05)   # po London open → ne
    db.add(DailyBias(ticker_id=t.id, bias_date=day, prob_down=.2, prob_neutral=.3, prob_up=.5, direction="up",
                     trust_score=60, n_news=3, avg_confidence=.8))
    db.add(DailyBias(ticker_id=t.id, bias_date=date(2026, 10, 17), prob_down=.3, prob_neutral=.4, prob_up=.3,
                     direction="neutral", trust_score=10, n_news=0, avg_confidence=0))      # sobota
    await db.commit()

    assert await bs.fill_v2_missing(db) == 1                   # víkend se přeskočí
    b = (await db.get(DailyBias, 1))
    assert b.v2_direction == "down" and b.v2_n_news == 1 and b.v2_cats == "earnings"
    assert b.v2_score == pytest.approx(-0.5)
    assert await bs.fill_v2_missing(db) == 0                   # už doplněno


@pytest.mark.asyncio
async def test_v2_none_without_verified_categories(db_session):
    src, t, cats = await _setup(db_session)
    await _news(db_session, src, t, cats["pmi"], datetime(2026, 10, 14, 5), .7, .1)
    db_session.add(DailyBias(ticker_id=t.id, bias_date=date(2026, 10, 14), prob_down=.1, prob_neutral=.2, prob_up=.7,
                             direction="up", trust_score=60, n_news=1, avg_confidence=.8))
    await db_session.commit()
    await bs.fill_v2_missing(db_session)
    b = await db_session.get(DailyBias, 1)
    assert b.v2_direction == "none" and b.v2_n_news == 0


@pytest.mark.asyncio
async def test_old_days_evaluated_from_hourly_bars(db_session, monkeypatch):
    t = Ticker(symbol="NQ", name="NQ", asset_class="futures", source_symbol_map={}, neutral_threshold=0.001)
    db_session.add(t)
    await db_session.commit()
    today = date.today()
    old = next(today - timedelta(days=d) for d in range(80, 90) if (today - timedelta(days=d)).weekday() < 5)
    db_session.add(DailyBias(ticker_id=t.id, bias_date=old, prob_down=.2, prob_neutral=.3, prob_up=.5,
                             direction="up", trust_score=50, n_news=3, avg_confidence=.5))
    await db_session.commit()
    lo = bs.london_open_utc(old).replace(tzinfo=timezone.utc).timestamp()
    cl = bs.ny_close_utc(old).replace(tzinfo=timezone.utc).timestamp()
    bars = [{"t": int(lo - 3600), "close": 100.0, "high": 100, "low": 100, "s": 3600},     # končí v London open
            {"t": int(lo), "close": 101.0, "high": 101, "low": 101, "s": 3600},
            {"t": int(cl - 3600), "close": 102.0, "high": 102, "low": 102, "s": 3600}]    # končí v 17:00 ET
    monkeypatch.setattr("app.sources.yahoo_finance_adapter.YahooFinanceAdapter.fetch_day_bars", lambda *a: [])
    monkeypatch.setattr("app.sources.yahoo_finance_adapter.YahooFinanceAdapter.fetch_hour_bars", lambda *a: bars)
    assert await bs.evaluate_pending(db_session, {t.id: t}) == 1
    b = await db_session.get(DailyBias, 1)
    assert b.realized_direction == "up" and b.realized_pct == pytest.approx(0.02)
    assert b.ny_realized_direction is None                     # NY session z hodinových barů nepočítáme


@pytest.mark.asyncio
async def test_stats_track_record_with_interval(db_session):
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    t = Ticker(symbol="NQ", name="NQ", asset_class="futures", source_symbol_map={}, neutral_threshold=0.001)
    db_session.add(t)
    await db_session.commit()
    start = date.today() - timedelta(days=60)
    days = [start + timedelta(days=i) for i in range(60) if (start + timedelta(days=i)).weekday() < 5][:20]
    for i, d in enumerate(days):
        db_session.add(DailyBias(ticker_id=t.id, bias_date=d, prob_down=.2, prob_neutral=.3, prob_up=.5,
                                 direction="up", trust_score=80, n_news=5, avg_confidence=.8,
                                 realized_direction="up" if i < 12 else "down",
                                 ny_realized_direction="up" if i < 10 else "down",
                                 v2_direction="up" if i < 8 else "none"))
    sat = next(start + timedelta(days=i) for i in range(7) if (start + timedelta(days=i)).weekday() == 5)
    db_session.add(DailyBias(ticker_id=t.id, bias_date=sat, prob_down=.2, prob_neutral=.3, prob_up=.5,
                             direction="up", trust_score=80, n_news=5, avg_confidence=.8,
                             realized_direction="down", ny_realized_direction="down"))
    await db_session.commit()
    from app.db import get_session

    async def same_session():
        yield db_session
    app.dependency_overrides[get_session] = same_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            tr = (await c.get("/api/bias/stats?ticker=NQ&days=90")).json()["track"]
    finally:
        app.dependency_overrides.pop(get_session, None)
    assert tr["ny"] == {"k": 10, "n": 20, "pct": 50.0, "ci": [29.9, 70.1], "coin": True}   # sobota se nepočítá
    assert tr["london"]["k"] == 12 and tr["london"]["n"] == 20
    assert tr["v2"]["london"]["n"] == 8 and tr["v2"]["london"]["pct"] == 100.0 and tr["v2"]["signal_days"] == 8
