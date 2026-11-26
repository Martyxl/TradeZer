"""publish_stats: denní close instrumentů Dashboardu pro sezónnost (Yahoo → prices/history)."""
import os
import sys
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "data"))
import publish_stats as pub  # noqa: E402


def _ts(d: str, h: int = 0) -> int:
    return int(datetime.fromisoformat(d).replace(hour=h, tzinfo=timezone.utc).timestamp())


def test_seasonal_since():
    assert pub.seasonal_since(date(2026, 11, 26)) == "2023-12-01"


def test_daily_bars_filters_dates_and_empty_closes():
    chart = {"chart": {"result": [{
        "timestamp": [_ts("2023-11-30"), _ts("2023-12-29"), _ts("2024-01-02"), _ts("2024-01-02", 22), _ts("2024-01-03")],
        "indicators": {"quote": [{"close": [1.0, 2.0, 3.0, 3.5, None]}]},
    }]}}
    assert pub.daily_bars(chart, "2023-12-01") == [
        {"date": "2023-12-29", "close": 2.0},
        {"date": "2024-01-02", "close": 3.5},       # víc záznamů ve dni → poslední
    ]


def test_all_dashboard_instruments_mapped():
    assert set(pub.SEASONAL) == {"NQ", "ES", "YM", "XAUUSD", "EURUSD", "GBPUSD", "USDJPY"}
