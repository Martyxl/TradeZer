"""SEC parser test — parse_companyfacts z XBRL (offline, bez sítě)."""
from app.valuation.providers.sec_provider import parse_companyfacts


def _flow(vals):
    """vals = list of (fy, fp, start, end, val, filed) → XBRL USD fakty."""
    return {"units": {"USD": [
        {"fy": fy, "fp": fp, "start": s, "end": e, "val": v, "filed": f, "form": "10-Q" if fp != "FY" else "10-K"}
        for (fy, fp, s, e, v, f) in vals]}}


def _instant(vals):
    return {"units": {"USD": [
        {"fy": fy, "fp": fp, "end": e, "val": v, "filed": f} for (fy, fp, e, v, f) in vals]}}


def _shares(vals):
    return {"units": {"shares": [
        {"fy": fy, "fp": fp, "start": s, "end": e, "val": v, "filed": f,
         "form": "10-Q" if fp != "FY" else "10-K"} for (fy, fp, s, e, v, f) in vals]}}


def _facts():
    rev = _flow([
        (2025, "Q1", "2025-01-01", "2025-03-31", 100, "2025-05-01"),
        (2025, "Q2", "2025-04-01", "2025-06-30", 110, "2025-08-01"),
        (2025, "Q3", "2025-07-01", "2025-09-30", 120, "2025-11-01"),
        (2025, "FY", "2025-01-01", "2025-12-31", 500, "2026-02-01"),  # Q4 = 500-330 = 170
        # YTD šum (6měsíční) se stejným fp=Q2 — musí být odfiltrován dle délky
        (2025, "Q2", "2025-01-01", "2025-06-30", 210, "2025-08-01"),
    ])
    ni = _flow([
        (2025, "Q1", "2025-01-01", "2025-03-31", 20, "2025-05-01"),
        (2025, "Q2", "2025-04-01", "2025-06-30", 22, "2025-08-01"),
        (2025, "Q3", "2025-07-01", "2025-09-30", 24, "2025-11-01"),
        (2025, "FY", "2025-01-01", "2025-12-31", 100, "2026-02-01"),  # Q4 NI = 34
    ])
    shares = _shares([
        (2025, "Q1", "2025-01-01", "2025-03-31", 1000, "2025-05-01"),
        (2025, "Q2", "2025-04-01", "2025-06-30", 1000, "2025-08-01"),
        (2025, "Q3", "2025-07-01", "2025-09-30", 1000, "2025-11-01"),
        (2025, "FY", "2025-01-01", "2025-12-31", 1000, "2026-02-01"),
    ])
    equity = _instant([
        (2025, "Q1", "2025-03-31", 600, "2025-05-01"),
        (2025, "FY", "2025-12-31", 650, "2026-02-01"),
    ])
    return {"facts": {"us-gaap": {
        "Revenues": rev, "NetIncomeLoss": ni,
        "WeightedAverageNumberOfDilutedSharesOutstanding": shares,
        "StockholdersEquity": equity,
    }}}


def test_quarterly_extraction_and_q4_derivation():
    stmts = parse_companyfacts(_facts())
    by_end = {s.period_end: s for s in stmts}
    # 4 kvartály 2025
    assert "2025-03-31" in by_end and "2025-12-31" in by_end
    assert by_end["2025-03-31"].revenue == 100
    # Q4 dopočet = 500 - (100+110+120) = 170
    assert by_end["2025-12-31"].revenue == 170
    # NI Q4 = 100 - (20+22+24) = 34
    assert by_end["2025-12-31"].net_income == 34


def test_ytd_noise_filtered():
    # 6měsíční Q2 fakt (210) nesmí přebít 3měsíční (110)
    stmts = parse_companyfacts(_facts())
    q2 = next(s for s in stmts if s.period_end == "2025-06-30")
    assert q2.revenue == 110


def test_eps_from_ni_over_shares():
    stmts = parse_companyfacts(_facts())
    q1 = next(s for s in stmts if s.period_end == "2025-03-31")
    assert abs(q1.eps_diluted - 20 / 1000) < 1e-6


def test_instant_balance_mapped():
    stmts = parse_companyfacts(_facts())
    q4 = next(s for s in stmts if s.period_end == "2025-12-31")
    assert q4.total_equity == 650   # FY-tagged rozvaha = konec roku


def test_empty_facts_no_crash():
    assert parse_companyfacts({"facts": {"us-gaap": {}}}) == []
