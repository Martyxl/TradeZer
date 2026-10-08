"""Sken portfolia: historie se posílá jednou (2y) a pak jednou denně (1mo), ne každou hodinu."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "data"))
import portfolio_quotes_scan as ps  # noqa: E402


def test_history_plan():
    assert ps.history_plan({}, "AAPL", "2026-10-08") == ("2y", True)                       # nový symbol → 2 roky
    assert ps.history_plan({"AAPL": "2026-10-07"}, "AAPL", "2026-10-08") == ("1mo", True)  # nový den → měsíc
    assert ps.history_plan({"AAPL": "2026-10-08"}, "AAPL", "2026-10-08") == ("5d", False)  # dnes už hotovo


def test_run_once_pushes_history_only_when_needed(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "HIST_STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(ps, "time", type("T", (), {"sleep": staticmethod(lambda s: None),
                                                    "strftime": staticmethod(lambda *a: "2026-10-08"),
                                                    "gmtime": staticmethod(lambda *a: None)}))
    monkeypatch.setattr(ps, "held_symbols", lambda b, t: (["AAPL", "MSFT"], ["USD", "CZK"]))
    fetched, hist_pushed, quote_pushes = [], [], []

    def fake_fetch(sym, rng="2y"):
        fetched.append((sym, rng))
        return {"symbol": sym.upper(), "price": 1.0, "currency": "USD"}, [{"date": "2026-10-07", "close": 1.0}]

    monkeypatch.setattr(ps, "_fetch", fake_fetch)
    monkeypatch.setattr(ps, "push_history", lambda b, t, s, bars: hist_pushed.append(s) or True)
    monkeypatch.setattr(ps, "push", lambda b, t, q: quote_pushes.append(len(q)))

    ps.run_once("http://x", "t")                         # 1. běh: vše nové → 2y historie (2 akcie + USDCZK)
    assert sorted(hist_pushed) == ["AAPL", "MSFT", "USDCZK"]
    assert all(r == "2y" for _, r in fetched)
    hist_pushed.clear(); fetched.clear()

    ps.run_once("http://x", "t")                         # 2. běh stejný den (další hodina) → jen ceny
    assert hist_pushed == []
    assert all(r == "5d" for _, r in fetched)
    assert quote_pushes[-1] == 3                         # živé ceny se pushují pořád (2 akcie + FX)

    monkeypatch.setattr(ps.time, "strftime", staticmethod(lambda *a: "2026-10-09"))
    ps.run_once("http://x", "t")                         # další den → jednou měsíc historie
    assert sorted(hist_pushed) == ["AAPL", "MSFT", "USDCZK"]
    assert all(r == "1mo" for _, r in fetched[-3:])
