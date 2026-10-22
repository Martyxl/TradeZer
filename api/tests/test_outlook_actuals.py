"""Vyhodnocení outlooku: skutečná hodnota z investingLive, když kalendář (FF mirror) `actual` nemá."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import NewsSource, OutlookEval, Ticker
from app.repositories import NewsRepository
from app.services import outlook_service


@pytest.mark.asyncio
async def test_eval_fills_actual_from_investinglive(db_session, monkeypatch):
    ev = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(second=0, microsecond=0)
    t = Ticker(symbol="NQ", name="NQ", asset_class="futures", source_symbol_map={}, neutral_threshold=0.001)
    src = NewsSource(name="rss_investinglive", source_weight=0.85, config={})
    db_session.add_all([t, src])
    await db_session.commit()
    await NewsRepository(db_session).create_news_item(
        source_id=src.id, external_id="il1", title="US initial jobless claims 194K vs 200K estimate",
        body="", url="u", published_at=(ev + timedelta(minutes=3)).replace(tzinfo=None), raw_payload={})
    await db_session.commit()

    async def events(**_):
        return [{"title": "Unemployment Claims", "currency": "USD", "impact": "high",
                 "time_utc": ev.strftime("%Y-%m-%dT%H:%M:00Z"), "forecast": "200K", "actual": ""}]
    monkeypatch.setattr(outlook_service, "get_upcoming_events", events)
    ts = int(ev.timestamp())
    bars = [{"t": ts + 300 * i, "close": 100.0 + 0.05 * i} for i in range(-6, 20)]
    monkeypatch.setattr("app.sources.yahoo_finance_adapter.YahooFinanceAdapter.fetch_day_bars",
                        lambda self, sym, d: bars)

    res = await outlook_service.evaluate_outlook(db_session)
    assert res["created"] == 1
    row = await db_session.scalar(select(OutlookEval))
    assert row.actual == "194K" and row.realized_bucket == "inline"   # 194 vs 200 = −3 % (tolerance ±5 %)
    assert row.actual_dir in ("up", "down", "flat") and row.price_move_pct is not None
