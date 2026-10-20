"""Bias: pondělní okno zpráv sahá od pátečního close (víkendové zprávy se počítají)."""
from datetime import date, datetime

from app.services.bias_service import _day_start_utc


def test_monday_window_starts_friday_close():
    monday = date(2026, 10, 19)
    assert monday.weekday() == 0
    assert _day_start_utc(monday) == datetime(2026, 10, 16, 22, 0)   # pátek 22:00 UTC


def test_midweek_window_unchanged():
    for d in (date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22), date(2026, 10, 23)):
        assert _day_start_utc(d) == datetime(d.year, d.month, d.day - 1, 22, 0)
