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


def test_missing_time_is_empty():
    d = {k: v for k, v in SHORT.items() if k != "traded_at"}
    assert _map_extracted(d, None)["traded_at"] == ""
