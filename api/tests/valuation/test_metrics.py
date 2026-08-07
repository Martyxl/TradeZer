"""P2 testy — čisté metrické funkce (bez I/O, bez sítě)."""
from datetime import date

from app.valuation import metrics as M
from app.valuation.peer import peer_zscores


def _q(pe, eps=1.0, rev=100.0, **kw):
    base = dict(period_end=pe, report_date=pe, revenue=rev, gross_profit=40.0,
                operating_income=25.0, ebitda=30.0, net_income=20.0, eps_diluted=eps,
                shares_diluted=1000.0, cfo=27.0, capex=-3.0, total_debt=50.0,
                cash_and_equivalents=10.0, total_equity=60.0)
    base.update(kw)
    return base


def test_ttm_sums_last_four():
    qs = [_q(date(2026, 3, 31), eps=1.5), _q(date(2025, 12, 31), eps=2.1),
          _q(date(2025, 9, 30), eps=1.48), _q(date(2025, 6, 30), eps=1.35),
          _q(date(2025, 3, 31), eps=1.2)]
    assert abs(M.ttm(qs, "eps_diluted") - (1.5 + 2.1 + 1.48 + 1.35)) < 1e-9


def test_ttm_none_when_fewer_than_four():
    qs = [_q(date(2026, 3, 31)), _q(date(2025, 12, 31))]
    assert M.ttm(qs, "eps_diluted") is None


def test_safe_div_edges():
    assert M.safe_div(10, 0) is None
    assert M.safe_div(None, 5) is None
    assert M.safe_div(10, 5) == 2.0


def test_negative_eps_gives_null_pe():
    qs = [_q(date(2026, 3, 31), eps=-0.5), _q(date(2025, 12, 31), eps=-0.5),
          _q(date(2025, 9, 30), eps=-0.5), _q(date(2025, 6, 30), eps=-0.5)]
    ms = M.compute_metrics("X", date(2026, 6, 1), 100.0, qs, [], {}, {}, [], [])
    assert ms.pe_ttm is None  # záporný TTM EPS → NULL, ne výjimka


def test_negative_ebitda_gives_null_ev_ebitda():
    qs = [_q(date(2026, 3, 31), ebitda=-5.0), _q(date(2025, 12, 31), ebitda=-5.0),
          _q(date(2025, 9, 30), ebitda=-5.0), _q(date(2025, 6, 30), ebitda=-5.0)]
    ms = M.compute_metrics("X", date(2026, 6, 1), 100.0, qs, [], {}, {}, [], [])
    assert ms.ev_ebitda is None


def test_pe_monotonic_in_close():
    qs = [_q(date(2026, 3, 31)), _q(date(2025, 12, 31)), _q(date(2025, 9, 30)), _q(date(2025, 6, 30))]
    low = M.compute_metrics("X", date(2026, 6, 1), 100.0, qs, [], {}, {}, [], [])
    high = M.compute_metrics("X", date(2026, 6, 1), 200.0, qs, [], {}, {}, [], [])
    assert high.pe_ttm > low.pe_ttm


def test_eps_ntm_weighting():
    # 6 měsíců do konce FY (prosinec, dnes červen) → 50/50 mix
    v = M.eps_ntm(7.0, 8.0, fy_end_month=12, today=date(2026, 6, 30))
    assert abs(v - 7.5) < 1e-9


def test_missing_inputs_never_raise():
    ms = M.compute_metrics("X", date(2026, 6, 1), None, [], [], {}, {}, [], [])
    assert ms.pe_ttm is None and ms.market_cap is None


def test_peer_zscore_median_mad_winsor():
    vals = {"A": 10.0, "B": 12.0, "C": 14.0, "D": 16.0, "E": 100.0}
    z = peer_zscores(vals)
    assert z["C"] == 0.0                      # medián → z=0
    assert z["E"] == 3.0                      # extrém winsorizován na +3
    assert all(-3.0 <= v <= 3.0 for v in z.values() if v is not None)


def test_peer_zscore_needs_five():
    assert all(v is None for v in peer_zscores({"A": 1.0, "B": 2.0}).values())
