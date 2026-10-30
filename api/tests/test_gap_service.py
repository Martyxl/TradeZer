"""Gap statistika: zavření / pokračování podle velikosti gapu + NY session vyhodnocení biasu."""
from datetime import date, datetime, timedelta, timezone

from app.models import DailyBias
from app.services import bias_service, gap_service


def _row(d, o, h, low, c):
    return {"d": d, "o": o, "h": h, "l": low, "c": c}


def test_compute_table_fill_and_continuation():
    d0 = date(2026, 1, 5)
    rows = [_row(d0, 100, 101, 99, 100)]
    # gap nahoru 0,05 % zavřený, gap dolů 1,5 % nezavřený a pokračuje dolů, gap nahoru 3 % zavřený
    rows.append(_row(d0 + timedelta(1), 100.05, 100.5, 99.9, 100.2))
    rows.append(_row(d0 + timedelta(2), 98.7, 99.0, 97.0, 97.5))
    rows.append(_row(d0 + timedelta(3), 100.43, 101.0, 97.4, 98.0))
    t = gap_service.compute_table(rows)
    by = {(r["lo"]): r for r in t["rows"]}
    assert t["n_days"] == 3
    assert by[0.0]["n"] == 1 and by[0.0]["fill_pct"] == 100 and by[0.0]["up"]["n"] == 1
    assert by[1.0]["down"] == {**by[1.0]["down"], "n": 1, "fill_pct": 0, "cont_pct": 100}
    assert by[2.0]["n"] == 1 and by[2.0]["fill_pct"] == 100 and by[2.0]["cont_pct"] == 0
    # dnešní (neuzavřený) den se do statistiky nepočítá
    assert gap_service.compute_table(rows, today=d0 + timedelta(3))["n_days"] == 2


def test_ny_session_realized_ignores_premarket():
    d = date(2026, 10, 29)   # EDT: NY open 13:30 UTC
    o = datetime(2026, 10, 29, 13, 30, tzinfo=timezone.utc).timestamp()
    pre = [{"t": o - 3600 * k, "close": 120.0, "high": 120.0, "low": 120.0} for k in range(1, 4)]
    rth = [{"t": o + 300 * i, "close": 100.0 - 0.1 * i, "high": 100.0, "low": 99.0} for i in range(78)]
    b = DailyBias(ticker_id=1, bias_date=d, prob_down=0.2, prob_neutral=0.2, prob_up=0.6, direction="up")
    bias_service._record_ny_session(b, pre + rth, neutral_threshold=0.001)
    assert b.ny_realized_direction == "down" and b.ny_realized_pct < 0
