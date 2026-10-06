"""Mapování vision extrakce → formulář deníku: výsledek (win/loss), čas, SL/TP."""
from app.routers.journal import _map_extracted

SHORT = {"instrument": "NASDAQ 100", "direction": "short", "entry": 31159.09,
         "stop": 31167.22, "target": 31101.05, "rr": 7.14,
         "traded_at": "2026-10-06T11:09"}


def test_loss_is_minus_one_r_at_stop():
    out = _map_extracted({**SHORT, "outcome": "loss"}, "http://x")
    assert out["r_result"] == -1.0
    assert out["exit_price"] == 31167.22  # SL
    assert out["traded_at"] == "2026-10-06T11:09"
    assert "SL: 31167.22" in out["notes"] and "TP: 31101.05" in out["notes"]
    assert "LOSS" in out["notes"]


def test_win_uses_planned_rr_at_target():
    out = _map_extracted({**SHORT, "outcome": "win"}, None)
    assert out["r_result"] == 7.14
    assert out["exit_price"] == 31101.05  # TP


def test_open_or_unknown_is_not_a_win():
    """Dřív se plánované RR ukládalo jako výsledek → každý obchod vypadal jako výhra."""
    for oc in ("open", None, ""):
        out = _map_extracted({**SHORT, "outcome": oc}, None)
        assert out["r_result"] is None and out["exit_price"] is None
        assert "neurčen" in out["notes"]


def test_sl_tp_outcome_are_separate_fields():
    out = _map_extracted({**SHORT, "outcome": "loss"}, None)
    assert out["stop_price"] == 31167.22 and out["target_price"] == 31101.05
    assert out["outcome"] == "loss"
    assert _map_extracted({**SHORT, "outcome": "open"}, None)["outcome"] == ""


def test_fill_result_from_levels_without_overwriting():
    from app.models.journal import JournalEntry
    from app.routers.journal import _fill_result, _outcome
    e = JournalEntry(instrument="NQ", direction="long", entry_price=100, stop_price=95,
                     target_price=110, outcome="win")
    _fill_result(e)
    assert e.exit_price == 110 and e.r_result == 2.0 and _outcome(e) == "win"
    e2 = JournalEntry(instrument="NQ", direction="long", entry_price=100, stop_price=95,
                      target_price=110, outcome="loss", r_result=-0.5, exit_price=97)
    _fill_result(e2)  # ruční hodnoty zůstanou
    assert e2.exit_price == 97 and e2.r_result == -0.5
    e3 = JournalEntry(instrument="NQ", direction="long", entry_price=100, stop_price=95, outcome="loss")
    _fill_result(e3)
    assert e3.exit_price == 95 and e3.r_result == -1.0


def test_missing_time_is_empty():
    d = {k: v for k, v in SHORT.items() if k != "traded_at"}
    assert _map_extracted(d, None)["traded_at"] == ""
