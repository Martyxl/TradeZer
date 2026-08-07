"""FMPProvider mapping test — offline, _get zmockovaný (nesíťuje)."""
import pytest

from app.valuation.providers.fmp_provider import FMPProvider


@pytest.fixture
def provider(monkeypatch):
    p = FMPProvider()
    responses = {
        "profile": [{"companyName": "Apple Inc.", "exchange": "NASDAQ", "currency": "USD",
                     "sector": "Technology", "industry": "Consumer Electronics",
                     "sharesOutstanding": 15000000000}],
        "income-statement": [
            {"date": "2026-03-31", "filingDate": "2026-05-01", "revenue": 95000000000,
             "grossProfit": 43000000000, "operatingIncome": 28000000000, "ebitda": 30000000000,
             "netIncome": 24000000000, "epsDiluted": 1.55, "weightedAverageShsOutDil": 15100000000}],
        "balance-sheet-statement": [
            {"date": "2026-03-31", "totalDebt": 105000000000,
             "cashAndCashEquivalents": 30000000000, "totalStockholdersEquity": 62000000000}],
        "cash-flow-statement": [
            {"date": "2026-03-31", "operatingCashFlow": 27000000000, "capitalExpenditure": -3000000000}],
        "analyst-estimates": [
            {"date": "2026-12-31", "estimatedEpsAvg": 7.2, "estimatedEpsLow": 6.9,
             "estimatedEpsHigh": 7.5, "numberAnalystEstimatedEps": 30}],
        "earnings": [{"date": "2026-03-31", "epsActual": 1.55, "epsEstimated": 1.50}],
        "historical-price-eod/full": [
            {"date": "2026-06-01", "open": 212, "high": 215, "low": 211, "close": 214, "volume": 48000000}],
    }
    monkeypatch.setattr(p, "_get", lambda path, **kw: responses.get(path, []))
    return p


def test_profile(provider):
    prof = provider.get_profile("AAPL")
    assert prof.name == "Apple Inc." and prof.gics_sector == "Technology"
    assert prof.shares_outstanding == 15000000000


def test_financials_join(provider):
    fins = provider.get_financials("AAPL")
    q = [f for f in fins if f.period_type == "Q"][0]
    assert q.revenue == 95000000000
    assert q.total_debt == 105000000000       # z balance
    assert q.cfo == 27000000000               # z cashflow
    assert q.report_date == "2026-05-01"


def test_estimates_mapped_to_horizon(provider):
    ests = provider.get_estimates("AAPL")
    eps = [e for e in ests if e.metric == "eps"]
    assert eps and eps[0].horizon in ("current_y", "next_y")
    assert eps[0].avg == 7.2 and eps[0].n_analysts == 30


def test_earnings_surprise_computed(provider):
    earn = provider.get_earnings_history("AAPL")
    assert earn[0].eps_actual == 1.55
    assert abs(earn[0].surprise_pct - 3.33) < 0.05


def test_prices(provider):
    px = provider.get_prices("AAPL", __import__("datetime").date(2026, 1, 1), __import__("datetime").date(2026, 12, 31))
    assert px[0].close == 214 and px[0].adj_close == 214


def test_missing_endpoint_returns_empty(monkeypatch):
    p = FMPProvider()
    monkeypatch.setattr(p, "_get", lambda path, **kw: (_ for _ in ()).throw(RuntimeError("403 premium")))
    assert p.get_estimates("AAPL") == []      # _safe spolkne chybu premium endpointu
    assert p.get_revisions("AAPL") == []
