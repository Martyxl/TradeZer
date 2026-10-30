"""Výsledky hospodaření: ingest z workeru (SEC 8-K) → AI vysvětlení, reakce ceny, feed."""
import os
from datetime import datetime, timedelta

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
from app.models import NewsItem, NewsSource
from app.valuation import earnings as E
from app.valuation.models import ValInstrument
from tests._auth import auth_headers

TOKEN = {"X-Internal-Token": "test-token"}


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def test_aliases_and_title_matching():
    names = E.aliases("GOOGL", "Alphabet Inc.")
    assert E._matches("Alphabet Q3 Profit Falls Despite 25% Revenue Growth", names)
    assert E._matches("Why Google stock is falling", names)
    assert not E._matches("Metal prices rally", E.aliases("META", "Meta Platforms, Inc."))
    assert E._matches("META shares slide after capex guidance", E.aliases("META", "Meta Platforms, Inc."))
    assert "Costco" in E.aliases("COST", "COSTCO WHOLESALE CORP /NEW")


@pytest.mark.asyncio
async def test_ingest_reaction_and_feed(monkeypatch):
    accepted = datetime.utcnow() - timedelta(hours=2)
    async with session_context() as s:
        s.add(ValInstrument(ticker="GOOGL", name="Alphabet Inc.", in_display_universe=True))
        src = NewsSource(name="rss_nasdaq", source_weight=0.5, config={})
        s.add(src)
        await s.commit()
        s.add(NewsItem(source_id=src.id, external_id="n1", title="Alphabet Q3 Profit Falls Despite 25% Revenue Growth",
                       body="", url="u1", published_at=accepted + timedelta(minutes=16), raw_payload={}))
        s.add(NewsItem(source_id=src.id, external_id="n2", title="Fed holds rates", body="", url="u2",
                       published_at=accepted + timedelta(minutes=20), raw_payload={}))
        await s.commit()

    calls = []

    def fake_json(system, user, max_tokens=1400):
        calls.append(user)
        return ({"fiscal_period": "Q3 2026", "revenue_usd": 102.3e9, "revenue_yoy_pct": 25, "eps_gaap": 2.12, "eps_adjusted": None,
                 "verdict": "mixed", "headline_cs": "Tržby rostou, zisk pod odhadem.",
                 "summary_cs": ["Tržby +25 %", "Zisk na akcii 2,12 USD pod odhadem 2,94"], "guidance_cs": None},
                "test-model")
    monkeypatch.setattr(E, "_llm_json", fake_json)
    monkeypatch.setattr(E, "_llm_text", lambda system, user, max_tokens=600: "- Investoři řeší výdaje na AI.")

    async with _client() as c:
        body = {"ticker": "googl", "accession": "0001652044-26-000080", "accepted_at": accepted.isoformat() + "Z",
                "url": "https://www.sec.gov/x", "press_text": "Alphabet announces third quarter 2026 results...",
                "eps_estimate": 2.94, "n_estimates": "14"}
        assert (await c.post("/api/valuation/earnings/ingest", json=body)).status_code in (401, 403, 503)
        r = (await c.post("/api/valuation/earnings/ingest", json=body, headers=TOKEN)).json()
        assert r["status"] == "created" and r["analyzed"]
        assert (await c.post("/api/valuation/earnings/ingest", json=body, headers=TOKEN)).json()["status"] == "exists"
        assert "Konsenzus EPS analytiků: 2.94" in calls[0]

        rr = (await c.post(f"/api/valuation/earnings/{r['id']}/reaction",
                           json={"price_before": 280.0, "price_now": 266.0}, headers=TOKEN)).json()
        assert rr["reaction_pct"] == -5.0 and rr["explained"]

        h = await auth_headers(c, "t@x.cz", plan="trader")
        feed = (await c.get("/api/valuation/earnings", headers=h)).json()["reports"]
        assert len(feed) == 1
        rep = feed[0]
        assert rep["name"] == "Alphabet Inc." and rep["verdict"] == "mixed" and rep["eps_actual"] == 2.12
        assert rep["eps_surprise_pct"] == pytest.approx(-27.89, abs=0.01)
        assert rep["summary_cs"].startswith("- Tržby +25 %")
        assert [n["title"] for n in rep["related_news"]] == ["Alphabet Q3 Profit Falls Despite 25% Revenue Growth"]
        assert rep["reaction_cs"].startswith("- Investoři")
        one = (await c.get("/api/valuation/GOOGL/earnings", headers=h)).json()
        assert one["ticker"] == "GOOGL" and len(one["reports"]) == 1
        free = await auth_headers(c, "f@x.cz")
        assert (await c.get("/api/valuation/earnings", headers=free)).status_code == 403
