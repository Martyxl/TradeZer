from datetime import date

from app.services import seasonality as S


def test_year_curves_base_from_previous_december():
    bars = [("2025-12-30", 100.0), ("2026-01-02", 110.0), ("2026-02-02", 90.0)]
    c = S.year_curves(bars, [2026])
    assert c["2026"] == [[0, 0.0], [1, 10.0], [32, -10.0]]


def test_year_curves_without_previous_year_starts_at_first_january_close():
    c = S.year_curves([("2025-01-03", 50.0), ("2025-01-06", 55.0)], [2025])
    assert c["2025"] == [[2, 0.0], [5, 10.0]]


def test_year_curves_skips_year_with_late_start_or_no_data():
    bars = [("2024-11-20", 10.0), ("2024-12-02", 11.0), ("2025-01-02", 12.0)]
    c = S.year_curves(bars, [2024, 2025, 2026])
    assert "2024" not in c and "2026" not in c          # 2024 začíná až v listopadu, 2026 nemá data
    assert c["2025"] == [[1, 0.0]]                       # prosincový close je starší než 20. 12. → základ = 2. 1.


def test_season_years():
    assert S.season_years(date(2026, 11, 23)) == [2024, 2025, 2026]
