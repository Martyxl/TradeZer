"""Plán pro MT5 robota: text klíč=hodnota, směr z biasu, offset, dnešní high-impact zprávy relevantní měny."""
from datetime import datetime, timedelta

import pytest
import pytest_asyncio

from app.models import DailyBias, Ticker
from app.services import bias_service
from app.sources import forex_factory


@pytest_asyncio.fixture
async def client(db_session):
    """API klient nad testovací session (přes dependency override)."""
    from httpx import ASGITransport, AsyncClient
    from app.db import get_session
    from app.main import app

    async def _override():
        yield db_session
    app.dependency_overrides[get_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_plan_text_with_bias_offset_and_news(client, db_session, monkeypatch):
    t = Ticker(symbol="NQ", name="NQ", asset_class="futures", source_symbol_map={}, neutral_threshold=0.001)
    db_session.add(t)
    await db_session.commit()
    tday = bias_service._trading_day(datetime.utcnow())
    db_session.add(DailyBias(ticker_id=t.id, bias_date=tday, prob_down=.2, prob_neutral=.2, prob_up=.6,
                             direction="up", trust_score=64, n_news=9, avg_confidence=.7))
    await db_session.commit()
    day = tday.isoformat()

    async def events(**_):
        return [
            {"title": "ISM Manufacturing PMI", "currency": "USD", "impact": "high", "time_utc": f"{day}T14:00:00Z"},
            {"title": "German Ifo", "currency": "EUR", "impact": "high", "time_utc": f"{day}T08:00:00Z"},   # jiná měna
            {"title": "Pending Home Sales", "currency": "USD", "impact": "medium", "time_utc": f"{day}T14:00:00Z"},
            {"title": "NFP", "currency": "USD", "impact": "high", "time_utc": f"{(tday + timedelta(days=1)).isoformat()}T12:30:00Z"},
        ]
    monkeypatch.setattr(forex_factory, "get_upcoming_events", events)
    r = await client.get("/api/ea/plan?ticker=nq")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    kv = [l.split("=", 1) for l in r.text.strip().splitlines()]
    d = {k: v for k, v in kv if k != "news"}
    news = [v for k, v in kv if k == "news"]
    assert d["direction"] == "up" and d["date"] == day and float(d["offset_pct"]) == 0.25
    assert d["ny_open_utc"] == "13:30" and d["close_utc"] == "21:00" and d["news_ok"] == "1"
    assert news == [f"{day}T14:00:00Z|USD|ISM Manufacturing PMI"]


@pytest.mark.asyncio
async def test_plan_without_snapshot_and_unknown_ticker(client, db_session):
    db_session.add(Ticker(symbol="ES", name="ES", asset_class="futures", source_symbol_map={}, neutral_threshold=0.001))
    await db_session.commit()
    r = await client.get("/api/ea/plan?ticker=ES")
    assert "direction=none" in r.text and "offset_pct=0.0" in r.text
    assert (await client.get("/api/ea/plan?ticker=XXX")).status_code == 404
