"""Regrese incidentu z 11. 10. 2026: duplicitní external_id v jedné dávce (např. dvě vystoupení téhož
řečníka ve stejný den ve ForexFactory) shodilo CELÝ refresh na uq_source_external → žádné nové zprávy."""
from datetime import datetime
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select, func

from app.models import Ticker, NewsItem
from app.services.news_aggregator import NewsAggregator
from app.sources.base import RawNewsItem


def raw(ext, title, hint=("XAUUSD",)):
    return RawNewsItem(source="fake", external_id=ext, title=title, body="b", url="u",
                       published_at=datetime(2026, 10, 14, 8, 30), raw_payload={},
                       instruments_hint=list(hint))


@pytest_asyncio.fixture
async def agg(db_session):
    db_session.add(Ticker(symbol="XAUUSD", name="Gold", asset_class="commodity",
                          source_symbol_map={}, neutral_threshold=0.001))
    await db_session.commit()
    return NewsAggregator(db_session)


@pytest.mark.asyncio
async def test_duplicate_ids_in_one_batch_do_not_abort_refresh(agg, db_session, monkeypatch):
    src = SimpleNamespace(name="forex_factory", source_weight=0.9)
    batch = [raw("same", "ECB President Lagarde Speaks"),
             raw("same", "ECB President Lagarde Speaks"),          # druhé vystoupení, stejné ID
             raw("other", "Gold rallies on safe haven demand")]    # musí se uložit i PO duplicitě

    async def fake(*a, **k):
        return [(src, batch)]
    monkeypatch.setattr(agg, "_fetch_all_sources", fake)

    stats = await agg.refresh()
    assert stats["new"] == 2 and stats["skipped"] == 1
    n = await db_session.scalar(select(func.count()).select_from(NewsItem))
    assert n == 2

    # druhý refresh (dnešní cron) je idempotentní — nic nového, nic nespadne
    stats2 = await agg.refresh()
    assert stats2["new"] == 0
    assert await db_session.scalar(select(func.count()).select_from(NewsItem)) == 2


@pytest.mark.asyncio
async def test_race_collision_is_skipped_not_fatal(agg, db_session, monkeypatch):
    """Souběžný refresh (cron + fast-refresh) vloží položku PO našem lookupu → jen přeskočit, zbytek uložit."""
    from app.repositories import NewsRepository
    src = SimpleNamespace(name="rss_x", source_weight=0.5)

    async def fake(*a, **k):
        return [(src, [raw("a", "Gold up"), raw("b", "Gold down")])]
    monkeypatch.setattr(agg, "_fetch_all_sources", fake)

    # „někdo jiný“ už zprávu a uložil, ale náš lookup o ní neví (race mezi lookupem a insertem)
    db_src = await NewsRepository(db_session).get_or_create_source("rss_x")
    await NewsRepository(db_session).create_news_item(source_id=db_src.id, external_id="a", title="Gold up",
                                                      body="b", url="u", published_at=datetime(2026, 10, 14), raw_payload={})
    await db_session.commit()

    async def blind(self, source_id, ext_ids):
        return {}
    monkeypatch.setattr(NewsRepository, "get_known_external_ids", blind)

    stats = await agg.refresh()
    assert stats["new"] == 1 and stats["skipped"] == 1                  # b uložena, a přeskočena
    assert await db_session.scalar(select(func.count()).select_from(NewsItem)) == 2
