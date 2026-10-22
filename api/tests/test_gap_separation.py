"""Gap reakce (zprávy při zavřeném trhu) se nesmí mísit s běžnými: statistiky přesnosti, paměť vzorů
a prior predikcí je drží odděleně."""
from datetime import datetime, timedelta

import pytest
import pytest_asyncio

from app.models import (MarketReaction, NewsCategory, NewsItemCategory, NewsPrediction, NewsSource, Ticker)
from app.repositories import NewsRepository


@pytest_asyncio.fixture
async def world(db_session):
    t = Ticker(symbol="NQ", name="NQ", asset_class="futures", source_symbol_map={}, neutral_threshold=0.001)
    src = NewsSource(name="s", source_weight=1.0, config={})
    cat = NewsCategory(name="inflation")
    db_session.add_all([t, src, cat])
    await db_session.commit()
    return t, src, cat


async def _add(db, world, ext, *, gap, pred_up, realized):
    """Predikce (argmax podle pred_up) + reakce (realized) + kategorie."""
    t, src, cat = world
    repo = NewsRepository(db)
    item = await repo.create_news_item(source_id=src.id, external_id=ext, title=ext, body="", url="u",
                                       published_at=datetime.utcnow() - timedelta(days=1), raw_payload={})
    db.add(NewsPrediction(news_id=item.id, ticker_id=t.id, prob_down=0.1 if pred_up else 0.8,
                          prob_neutral=0.1, prob_up=0.8 if pred_up else 0.1))
    db.add(NewsItemCategory(news_id=item.id, category_id=cat.id))
    await db.commit()
    await repo.save_market_reaction(
        news_id=item.id, ticker_id=t.id, price_at_news=100.0, price_15m=101.0, price_1h=101.0, price_1d=None,
        pct_change_15m=0.01 if realized == "up" else -0.01, pct_change_1h=0.01, pct_change_1d=None,
        realized_direction=realized, price_series={"gap": gap}, is_gap=gap)
    await db.commit()


@pytest.mark.asyncio
async def test_accuracy_stats_separate_regular_and_gap(db_session, world):
    t = world[0]
    for i in range(3):   # běžné: 2 správně z 3
        await _add(db_session, world, f"r{i}", gap=False, pred_up=True, realized="up" if i < 2 else "down")
    for i in range(2):   # gap: 0 správně ze 2
        await _add(db_session, world, f"g{i}", gap=True, pred_up=True, realized="down")
    repo = NewsRepository(db_session)
    reg = await repo.get_accuracy_stats(t.id, days=30)
    gp = await repo.get_accuracy_stats(t.id, days=30, gap=True)
    assert (reg["total"], reg["correct"], reg["gap"]) == (3, 2, False)
    assert (gp["total"], gp["correct"], gp["gap"]) == (2, 0, True)
    assert reg["by_category"]["inflation"]["total"] == 3 and gp["by_category"]["inflation"]["total"] == 2


@pytest.mark.asyncio
async def test_patterns_and_prior_exclude_gap_by_default(db_session, world):
    t = world[0]
    for i in range(3):
        await _add(db_session, world, f"r{i}", gap=False, pred_up=True, realized="up")
    for i in range(4):
        await _add(db_session, world, f"g{i}", gap=True, pred_up=False, realized="down")
    repo = NewsRepository(db_session)
    pats = await repo.get_category_patterns(t.id, ["inflation"], days=30, min_samples=1)
    assert pats[0]["sample_count"] == 3 and pats[0]["dominant_direction"] == "up"
    gap_pats = await repo.get_category_patterns(t.id, ["inflation"], days=30, min_samples=1, gap=True)
    assert gap_pats[0]["sample_count"] == 4 and gap_pats[0]["dominant_direction"] == "down"
    prior = await repo.get_historical_direction_by_category("inflation", t.id)
    assert sum(prior.values()) == 3          # prior predikcí jen z běžných reakcí
