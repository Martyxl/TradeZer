"""Živý worker „den v číslech“ (data/edge_live.py) — víkendový útlum, mapování událostí, záložní zdroj."""
import os
import sys
from datetime import date, datetime

import pytest

pytest.importorskip("pandas")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "data"))
import edge_live as el  # noqa: E402


@pytest.mark.parametrize("when,quiet", [
    (datetime(2026, 11, 6, 17, 29, tzinfo=el.ET), True),    # pátek po RTH (mezi 16:35 a 19:55)
    (datetime(2026, 11, 6, 17, 30, tzinfo=el.ET), True),    # pátek 17:30 → víkend
    (datetime(2026, 11, 7, 12, 0, tzinfo=el.ET), True),     # sobota
    (datetime(2026, 11, 8, 15, 59, tzinfo=el.ET), True),    # neděle před 16:00
    (datetime(2026, 11, 8, 20, 0, tzinfo=el.ET), False),    # neděle večer = Asie pondělního dne
    (datetime(2026, 11, 9, 10, 0, tzinfo=el.ET), False),    # pondělí RTH
    (datetime(2026, 11, 9, 16, 40, tzinfo=el.ET), True),    # po zavření
])
def test_quiet_window(when, quiet):
    assert el.quiet(when) is quiet


def test_calendar_events_mapping(monkeypatch):
    monkeypatch.setattr(el, "_get_json", lambda url, *a, **k: {"events": [
        {"title": "CPI m/m"}, {"title": "Non-Farm Employment Change"}, {"title": "ISM Manufacturing PMI"},
        {"title": "Federal Funds Rate"}]})
    assert el.calendar_events() == ["cpi", "fomc", "nfp"]


def test_static_events_from_reference_file():
    assert el.static_events(date(2026, 10, 28)) == ["fomc"]
    assert el.static_events(date(2026, 10, 14)) == ["cpi"]
    assert el.static_events(date(2026, 10, 13)) == []


def test_fetch_falls_back_to_second_source(monkeypatch):
    import pandas as pd

    def boom(sym):
        raise RuntimeError("429")

    monkeypatch.setattr(el, "yahoo_bars", boom)
    monkeypatch.setattr(el, "td_bars", lambda sym: pd.DataFrame({"ts": [pd.Timestamp("2026-11-02 15:00", tz="UTC")],
                                                                 "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]}))
    src, df = el.fetch("nq")
    assert src == "twelvedata" and len(df) == 1
    monkeypatch.setattr(el, "td_bars", boom)
    with pytest.raises(RuntimeError, match="yahoo:429; twelvedata:429"):
        el.fetch("nq")
