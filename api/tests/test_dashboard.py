"""Agregovaný /api/dashboard: tvar částí je shodný s původními endpointy, části jsou izolované."""
import os
from datetime import datetime

import pytest

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["ANTHROPIC_API_KEY"] = "test-key"
os.environ["INTERNAL_API_TOKEN"] = "test-token"

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.base import Base
from app.db.engine import engine
from app.db.session import session_context
from app.models import Ticker, NewsSource
from app.repositories import NewsRepository


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_context() as s:
        s.add(Ticker(symbol="NQ", name="Nasdaq 100", asset_class="index", source_symbol_map={}, neutral_threshold=0.002))
        s.add(NewsSource(name="src", source_weight=0.8, config={}))
        await s.commit()
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_aggregate_matches_individual_endpoints():
    async with _client() as c:
        agg = (await c.get("/api/dashboard?ticker=nq")).json()          # ticker se normalizuje
        assert agg["ticker"] == "NQ" and agg["errors"] == []
        # Stejný tvar/obsah jako původní endpointy (na ně se frontend přesměrovává)
        assert agg["tickers"] == (await c.get("/api/tickers")).json()
        assert agg["regime"] == (await c.get("/api/regime")).json()
        assert agg["gamma"] == (await c.get("/api/gamma?ticker=NQ")).json()
        assert agg["events_today"] == (await c.get("/api/news/events/today")).json()
        assert agg["news"] == (await c.get("/api/news?ticker=NQ&limit=25&offset=0")).json() == []
        bt = (await c.get("/api/bias/today?ticker=NQ")).json()
        assert set(agg["bias_today"]) == set(bt) and agg["bias_today"]["ticker"] == "NQ"
        assert agg["bias_stats_30"] == (await c.get("/api/bias/stats?ticker=NQ&days=30")).json()
        assert agg["bias_stats_90"] == (await c.get("/api/bias/stats?ticker=NQ&days=90")).json()
        # chybějící denní summary = 404 u původního endpointu → null v agregátu (ne chyba)
        assert (await c.get("/api/summary/daily?ticker=NQ")).status_code == 404
        assert agg["summary"] is None


@pytest.mark.asyncio
async def test_news_items_have_same_shape_as_news_endpoint():
    async with session_context() as s:
        src = await s.scalar(__import__("sqlalchemy").select(NewsSource))
        repo = NewsRepository(s)
        await repo.create_news_item(source_id=src.id, external_id="1", title="Hello", body="b", url="u",
                                    published_at=datetime.utcnow(), raw_payload={})
    async with _client() as c:
        agg = (await c.get("/api/dashboard?ticker=NQ")).json()
        # položky bez vazby na ticker se v seznamu pro NQ neukazují — oba zdroje se musí shodnout
        assert agg["news"] == (await c.get("/api/news?ticker=NQ&limit=25&offset=0")).json()


@pytest.mark.asyncio
async def test_unknown_ticker_does_not_break_the_page():
    async with _client() as c:
        r = await c.get("/api/dashboard?ticker=ZZZ")
        assert r.status_code == 200
        d = r.json()
        assert d["tickers"] and d["bias_today"] is None and d["news"] is None and d["errors"] == []  # 404 = null


@pytest.mark.asyncio
async def test_failing_part_is_isolated(monkeypatch):
    from app.routers import bias as r_bias

    async def boom(**kw):
        raise RuntimeError("db hiccup")
    monkeypatch.setattr(r_bias, "bias_today", boom)
    async with _client() as c:
        d = (await c.get("/api/dashboard?ticker=NQ")).json()
        assert d["bias_today"] is None and any("bias_today" in e for e in d["errors"])
        assert d["tickers"] and d["bias_stats_30"] is not None      # ostatní části fungují dál


def test_cache_headers_dashboard_longer_than_default():
    from app.main import _cache_header
    assert "s-maxage=300" in _cache_header("/api/dashboard") and "stale-while-revalidate=3600" in _cache_header("/api/dashboard")
    assert "s-maxage=60" in _cache_header("/api/bias/today")
    assert _cache_header("/api/fund") is not None
    # interní a placené cesty se NIKDY necachují veřejně
    for p in ("/api/fund/signals", "/api/fund/ingest", "/api/investments/portfolio", "/api/journal",
              "/api/auth/me", "/api/valuation/overview", "/api/discovery"):
        assert _cache_header(p) is None, p
