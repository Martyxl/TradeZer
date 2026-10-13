"""Integrační testy pro NewsRepository."""
from datetime import datetime, date, timedelta

import pytest
import pytest_asyncio

from app.repositories import NewsRepository, TickerRepository
from app.models import Ticker, NewsSource


@pytest_asyncio.fixture
async def setup_data(db_session):
    ticker = Ticker(
        symbol="EURUSD", name="EUR/USD", asset_class="forex",
        source_symbol_map={}, neutral_threshold=0.002
    )
    db_session.add(ticker)
    source = NewsSource(name="test_source", source_weight=0.8, config={})
    db_session.add(source)
    await db_session.flush()
    await db_session.commit()
    return ticker, source


@pytest.mark.asyncio
async def test_create_and_retrieve_news_item(db_session, setup_data):
    ticker, source = setup_data
    repo = NewsRepository(db_session)

    item = await repo.create_news_item(
        source_id=source.id,
        external_id="test-001",
        title="ECB raises rates",
        body="ECB raised rates by 25bps",
        url="https://example.com/1",
        published_at=datetime.utcnow(),
        raw_payload={"test": True},
    )
    assert item.id is not None
    assert item.title == "ECB raises rates"

    retrieved = await repo.get_news_by_id(item.id)
    assert retrieved is not None
    assert retrieved.external_id == "test-001"


@pytest.mark.asyncio
async def test_unpredicted_min_age_filter(db_session, setup_data):
    """min_age_minutes = grace okno: čerstvé zprávy vynechá (nechá Sparku), staré vrátí."""
    _, source = setup_data
    repo = NewsRepository(db_session)
    await repo.create_news_item(source_id=source.id, external_id="fresh", title="Fresh",
                                body="", url="u1", published_at=datetime.utcnow(), raw_payload={})
    old = await repo.create_news_item(source_id=source.id, external_id="old", title="Old",
                                      body="", url="u2", published_at=datetime.utcnow(), raw_payload={})
    old.fetched_at = datetime.utcnow() - timedelta(minutes=30)
    await db_session.commit()

    # bez okna: obě nepredikované
    all_items = await repo.get_unpredicted_items(limit=10)
    assert {i.external_id for i in all_items} == {"fresh", "old"}
    # grace okno 10 min: jen stará (fresh je čerstvá → primárně pro Spark worker)
    aged = await repo.get_unpredicted_items(limit=10, min_age_minutes=10)
    assert {i.external_id for i in aged} == {"old"}


@pytest.mark.asyncio
async def test_idempotent_news_creation(db_session, setup_data):
    ticker, source = setup_data
    repo = NewsRepository(db_session)

    existing = await repo.get_news_item_by_external(source.id, "ext-unique-123")
    assert existing is None

    await repo.create_news_item(
        source_id=source.id,
        external_id="ext-unique-123",
        title="Test",
        body=None,
        url="https://example.com",
        published_at=datetime.utcnow(),
        raw_payload={},
    )
    await db_session.commit()

    existing_after = await repo.get_news_item_by_external(source.id, "ext-unique-123")
    assert existing_after is not None


@pytest.mark.asyncio
async def test_ticker_repository(db_session, setup_data):
    ticker, _ = setup_data
    repo = TickerRepository(db_session)

    found = await repo.get_by_symbol("EURUSD")
    assert found is not None
    assert found.name == "EUR/USD"

    all_tickers = await repo.get_all_enabled()
    assert len(all_tickers) >= 1


@pytest.mark.asyncio
async def test_high_impact_events_no_duplicates_and_no_distinct_on_json(db_session, setup_data):
    """Regrese: `SELECT DISTINCT` nad news_items (JSON sloupec) shazovalo /api/news/events/today
    na PostgreSQL (500). Dotaz nesmí DISTINCT obsahovat a zpráva ve 2 HIGH kategoriích je jednou."""
    from sqlalchemy.dialects import postgresql
    from app.models import NewsCategory, NewsItemCategory
    _, source = setup_data
    repo = NewsRepository(db_session)
    it = await repo.create_news_item(source_id=source.id, external_id="cpi", title="US CPI hot", body="",
                                     url="u", published_at=datetime.utcnow(), raw_payload={})
    other = await repo.create_news_item(source_id=source.id, external_id="x", title="Bakery", body="",
                                        url="u2", published_at=datetime.utcnow(), raw_payload={})
    inf, fed, misc = NewsCategory(name="inflation"), NewsCategory(name="fed_speech"), NewsCategory(name="sports")
    db_session.add_all([inf, fed, misc])
    await db_session.flush()
    db_session.add_all([NewsItemCategory(news_id=it.id, category_id=inf.id),
                        NewsItemCategory(news_id=it.id, category_id=fed.id),   # 2. HIGH kategorie → dřív duplicita
                        NewsItemCategory(news_id=other.id, category_id=misc.id)])
    await db_session.commit()

    day = it.published_at.date()   # explicitně (UTC vs lokální „dnes" se kolem půlnoci liší)
    events = await repo.get_high_impact_events(for_date=day)
    assert [e.title for e in events] == ["US CPI hot"]

    # SQL pro PostgreSQL nesmí obsahovat DISTINCT (JSON nemá rovnost)
    captured = {}
    orig = db_session.execute

    async def spy(stmt, *a, **k):
        if "news_items" in str(stmt) and "news_categories" in str(stmt):
            captured["sql"] = str(stmt.compile(dialect=postgresql.dialect()))
        return await orig(stmt, *a, **k)
    db_session.execute = spy
    await repo.get_high_impact_events(for_date=day)
    assert "DISTINCT" not in captured["sql"].upper()
