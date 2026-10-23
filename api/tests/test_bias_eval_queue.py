"""Vyhodnocení biasu: staré nevyhodnotitelné řádky nesmí zablokovat frontu (dřív limit 10 bez řazení)."""
from datetime import date, timedelta

import pytest

from app.models import DailyBias, Ticker
from app.services import bias_service


@pytest.mark.asyncio
async def test_newest_first_and_old_rows_do_not_starve(db_session, monkeypatch):
    t = Ticker(symbol="NQ", name="NQ", asset_class="futures", source_symbol_map={}, neutral_threshold=0.001)
    db_session.add(t)
    await db_session.commit()
    today = date.today()
    for d in range(15):   # 15 starých (mimo dosah dat) + 3 nové
        db_session.add(DailyBias(ticker_id=t.id, bias_date=today - timedelta(days=100 + d), prob_down=.3,
                                 prob_neutral=.4, prob_up=.3, direction="up", trust_score=50, n_news=3, avg_confidence=.5))
    for d in (2, 3, 4):
        db_session.add(DailyBias(ticker_id=t.id, bias_date=today - timedelta(days=d), prob_down=.3,
                                 prob_neutral=.4, prob_up=.3, direction="up", trust_score=50, n_news=3, avg_confidence=.5))
    await db_session.commit()
    asked = []

    def fake_bars(self, sym, d):
        asked.append(d)
        return []   # bez dat → nevyhodnotí, ale musí se aspoň zkusit nové dny
    monkeypatch.setattr("app.sources.yahoo_finance_adapter.YahooFinanceAdapter.fetch_day_bars", fake_bars)
    await bias_service.evaluate_pending(db_session, {t.id: t})
    assert sorted(asked, reverse=True) == [today - timedelta(days=d) for d in (2, 3, 4)]


@pytest.mark.asyncio
async def test_weekend_rows_skipped(db_session, monkeypatch):
    t = Ticker(symbol="ES", name="ES", asset_class="futures", source_symbol_map={}, neutral_threshold=0.001)
    db_session.add(t)
    await db_session.commit()
    today = date.today()
    sat = today - timedelta(days=(today.weekday() - 5) % 7 or 7)
    fri = sat - timedelta(days=1)
    for d in (sat, sat + timedelta(days=1), fri):
        db_session.add(DailyBias(ticker_id=t.id, bias_date=d, prob_down=.3, prob_neutral=.4, prob_up=.3,
                                 direction="up", trust_score=50, n_news=3, avg_confidence=.5))
    await db_session.commit()
    asked = []
    monkeypatch.setattr("app.sources.yahoo_finance_adapter.YahooFinanceAdapter.fetch_day_bars",
                        lambda self, sym, d: asked.append(d) or [])
    await bias_service.evaluate_pending(db_session, {t.id: t}, limit=1)
    assert asked == [fri]
