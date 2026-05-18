"""Integrační testy pro NewsRepository."""
from datetime import datetime, date

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
