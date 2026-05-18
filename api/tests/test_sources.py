"""Unit testy pro source adaptéry."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.sources.forex_factory import ForexFactoryAdapter
from app.sources.rss_adapter import RSSAdapter
from app.sources.newsapi_adapter import NewsAPIAdapter


FOREX_FACTORY_XML = """<?xml version="1.0" encoding="utf-8"?>
<weeklyevents>
  <week>
    <event id="1">
      <title>ECB Interest Rate Decision</title>
      <country>EUR</country>
      <date>05-15-2026 12:45pm</date>
      <impact>High</impact>
      <forecast>4.25%</forecast>
      <previous>4.00%</previous>
      <actual>4.50%</actual>
      <currency>EUR</currency>
      <description>European Central Bank rate decision</description>
    </event>
  </week>
</weeklyevents>"""


@pytest.mark.asyncio
async def test_forex_factory_parse():
    adapter = ForexFactoryAdapter()
    with patch.object(adapter, "_download_xml", new=AsyncMock(return_value=FOREX_FACTORY_XML)):
        items = await adapter.fetch()
    assert len(items) == 1
    item = items[0]
    assert "ECB" in item.title
    assert "EURUSD" in item.instruments_hint
    assert item.source == "forex_factory"


@pytest.mark.asyncio
async def test_forex_factory_filters_non_eur():
    xml = """<?xml version="1.0" encoding="utf-8"?>
<weeklyevents>
  <week>
    <event id="2">
      <title>Chinese Trade Balance</title>
      <currency>CNY</currency>
      <date>05-15-2026 02:00am</date>
      <impact>Medium</impact>
    </event>
  </week>
</weeklyevents>"""
    adapter = ForexFactoryAdapter()
    with patch.object(adapter, "_download_xml", new=AsyncMock(return_value=xml)):
        items = await adapter.fetch()
    assert len(items) == 0


@pytest.mark.asyncio
async def test_newsapi_skips_when_no_key():
    import app.sources.newsapi_adapter as module
    with patch.object(module.settings, "newsapi_key", ""):
        adapter = NewsAPIAdapter()
        items = await adapter.fetch()
    assert items == []


@pytest.mark.asyncio
async def test_rss_adapter_parses():
    import feedparser
    mock_feed = MagicMock()
    mock_feed.entries = [
        MagicMock(
            title="EUR/USD hits 3-month high",
            link="https://reuters.com/1",
            id="https://reuters.com/1",
            published="Thu, 15 May 2026 10:00:00 GMT",
            summary="EUR/USD reached a 3-month high...",
        )
    ]

    adapter = RSSAdapter(
        name="rss_test",
        url="https://example.com/rss",
        instruments_hint=["EURUSD"],
    )
    with patch.object(adapter, "_fetch_feed", new=AsyncMock(return_value=mock_feed)):
        items = await adapter.fetch()

    assert len(items) == 1
    assert "EUR/USD" in items[0].title
    assert "EURUSD" in items[0].instruments_hint
