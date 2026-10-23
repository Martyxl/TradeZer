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


def test_entry_pnl_measured_from_entry_not_london_open():
    from datetime import datetime, timezone
    b = DailyBias(ticker_id=1, bias_date=date(2026, 10, 14), prob_down=.2, prob_neutral=.2, prob_up=.6,
                  direction="up", trust_score=50, n_news=3, avg_confidence=.5)
    b.realized_pct = 0.05   # London→close +5 % (většina PŘED vstupem) — nesmí se započítat
    ny = int(datetime(2026, 10, 14, 13, 30, tzinfo=timezone.utc).timestamp())
    # open 100, protipohyb na 99.5 (fill limitu při offsetu 0.25 % = 99.75), close 100.0
    bars = [{"t": ny + 300 * i, "close": c, "high": c + 0.05, "low": c - 0.05}
            for i, c in enumerate([100, 99.8, 99.55, 99.7, 99.9, 100.0, 100.0, 100.0])]
    bias_service._record_ny_path(b, bars, "NQ", 0.001)
    assert b.entry_filled is True
    assert abs(b.entry_pnl_pct - (100.0 - 99.75) / 99.75 * 100) < 1e-3    # ≈ +0.25 %, ne +5 %
