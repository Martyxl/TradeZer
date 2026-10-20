"""Kalibrace: nevyhodnotitelné predikce se označí trvale, čekající (budoucí/čerstvé/chyba sítě) ne."""
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import MarketReaction, NewsPrediction, Ticker, NewsSource
from app.repositories import NewsRepository
from app.services.calibration_service import CalibrationService


@pytest_asyncio.fixture
async def world(db_session):
    t = Ticker(symbol="NQ", name="NQ", asset_class="futures", source_symbol_map={}, neutral_threshold=0.001)
    src = NewsSource(name="s", source_weight=1.0, config={})
    db_session.add_all([t, src])
    await db_session.commit()
    return t, src


async def _pred(db, world, ext, published_ago: timedelta):
    t, src = world
    repo = NewsRepository(db)
    item = await repo.create_news_item(source_id=src.id, external_id=ext, title=ext, body="", url="u",
                                       published_at=datetime.utcnow() - published_ago, raw_payload={})
    p = NewsPrediction(news_id=item.id, ticker_id=t.id, prob_down=.3, prob_neutral=.3, prob_up=.4)
    p.created_at = datetime.utcnow() - timedelta(hours=5)
    db.add(p)
    await db.commit()
    return item


def _bars_around(news_utc):
    base = int(news_utc.replace(tzinfo=timezone.utc).timestamp())
    return [{"t": base + 300 * i, "close": 100.0 + i * 0.1} for i in range(-6, 30)]


async def _reaction(db, news_id):
    return await db.scalar(select(MarketReaction).where(MarketReaction.news_id == news_id))


@pytest.mark.asyncio
async def test_too_old_marked_without_fetching(db_session, world):
    item = await _pred(db_session, world, "old", timedelta(days=90))
    svc = CalibrationService(db_session)
    svc.yahoo.fetch_day_bars = lambda *a, **k: pytest.fail("nemá stahovat")
    stats = await svc.run()
    assert stats["unresolvable"] == 1 and stats["recorded"] == 0
    assert (await _reaction(db_session, item.id)).skip_reason == "too_old"
    # příští běh už ji nevrací
    assert await NewsRepository(db_session).get_predictions_without_reactions(30, 65) == []


@pytest.mark.asyncio
async def test_future_and_fresh_events_wait(db_session, world):
    await _pred(db_session, world, "upcoming", timedelta(days=-3))   # event je za 3 dny
    await _pred(db_session, world, "fresh", timedelta(minutes=40))   # ještě neuplynula 1 h
    repo = NewsRepository(db_session)
    assert await repo.get_predictions_without_reactions(30, 65) == []
    svc = CalibrationService(db_session)
    svc.yahoo.fetch_day_bars = lambda *a, **k: pytest.fail("nemá stahovat")
    assert (await svc.run())["checked"] == 0


@pytest.mark.asyncio
async def test_weekend_no_bars_marked_but_network_error_retried(db_session, world):
    weekend = await _pred(db_session, world, "weekend", timedelta(days=2))
    svc = CalibrationService(db_session)
    svc.yahoo.fetch_day_bars = lambda *a, **k: []          # Yahoo: prázdno (trh zavřený)
    assert (await svc.run())["unresolvable"] == 1
    assert (await _reaction(db_session, weekend.id)).skip_reason == "no_data"

    err = await _pred(db_session, world, "neterr", timedelta(days=2))
    svc2 = CalibrationService(db_session)

    def boom(*a, **k):
        raise RuntimeError("yahoo down")
    svc2.yahoo.fetch_day_bars = boom
    s = await svc2.run()
    assert s["unresolvable"] == 0 and s["skipped"] == 1       # chyba sítě → nic se neoznačí
    assert await _reaction(db_session, err.id) is None


@pytest.mark.asyncio
async def test_normal_news_is_recorded(db_session, world):
    item = await _pred(db_session, world, "ok", timedelta(days=2))
    svc = CalibrationService(db_session)
    pub = item.published_at
    svc.yahoo.fetch_day_bars = lambda *a, **k: _bars_around(pub)
    stats = await svc.run()
    assert stats["recorded"] == 1 and stats["unresolvable"] == 0
    r = await _reaction(db_session, item.id)
    assert r.skip_reason is None and r.realized_direction is not None and r.price_at_news is not None
