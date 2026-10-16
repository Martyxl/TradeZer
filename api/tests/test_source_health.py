"""Kontrola zdrojů zpráv: probe feedu (200/403/chyba sítě) a přehled aktivity z DB."""
import os
from datetime import datetime, timedelta

import httpx
import pytest

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["ANTHROPIC_API_KEY"] = "test-key"
os.environ["INTERNAL_API_TOKEN"] = "test-token"

from app.services.source_health import probe_many, db_activity
from app.models import NewsSource
from app.repositories import NewsRepository

RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>Test feed</title>
<item><title>A</title><link>u1</link><pubDate>Fri, 16 Oct 2026 12:00:00 GMT</pubDate></item>
<item><title>B</title><link>u2</link><pubDate>Fri, 16 Oct 2026 13:30:00 GMT</pubDate></item>
</channel></rss>"""


def _handler(request: httpx.Request) -> httpx.Response:
    u = str(request.url)
    if "ok" in u:
        return httpx.Response(200, text=RSS)
    if "empty" in u:
        return httpx.Response(200, text="<rss version='2.0'><channel><title>x</title></channel></rss>")
    if "blocked" in u:
        return httpx.Response(403, text="Forbidden")
    raise httpx.ConnectError("dns")


@pytest.mark.asyncio
async def test_probe_classifies_feeds():
    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as c:
        res = {r["url"].split("//")[1]: r for r in await probe_many(
            ["http://ok.test/f", "http://empty.test/f", "http://blocked.test/f", "http://dead.test/f"], client=c)}
    assert res["ok.test/f"]["ok"] and res["ok.test/f"]["entries"] == 2
    assert res["ok.test/f"]["newest"] == "2026-10-16T13:30+00:00" and res["ok.test/f"]["title"] == "Test feed"
    assert res["empty.test/f"]["status"] == 200 and not res["empty.test/f"]["ok"]      # 200, ale prázdný = mrtvý
    assert res["blocked.test/f"]["status"] == 403 and not res["blocked.test/f"]["ok"]
    assert res["dead.test/f"]["status"] == 0 and res["dead.test/f"]["error"] == "ConnectError"


@pytest.mark.asyncio
async def test_db_activity_counts_recent_and_flags_dead_sources(db_session):
    repo = NewsRepository(db_session)
    alive = await repo.get_or_create_source("alive")
    await repo.get_or_create_source("dead")                       # zdroj bez jediné zprávy
    old_src = await repo.get_or_create_source("old")
    await repo.create_news_item(source_id=alive.id, external_id="1", title="t", body="", url="u",
                                published_at=datetime.utcnow(), raw_payload={})
    stale = await repo.create_news_item(source_id=old_src.id, external_id="2", title="t", body="", url="u",
                                        published_at=datetime.utcnow(), raw_payload={})
    stale.fetched_at = datetime.utcnow() - timedelta(days=3)
    await db_session.commit()
    rows = {r["source"]: r for r in await db_activity(db_session, 24)}
    assert rows["alive"]["stored_last_24h"] == 1
    assert rows["dead"]["stored_last_24h"] == 0 and rows["dead"]["last_stored"] is None
    assert rows["old"]["stored_last_24h"] == 0 and rows["old"]["last_stored"] is not None
