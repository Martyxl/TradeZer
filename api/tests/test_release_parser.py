"""Parser vydaných makro dat z titulků investingLive (reálné titulky z 9–10/2026)."""
import pytest

from app.services.release_parser import parse_release, release_context

CASES = [
    # titulek, actual, compare, kind, currency, inverse, strength
    ("US initial jobless claims 194K vs 200K estimate. Better than expected.", 194, 200, "forecast", "USD", True, 1),
    ("US September pending home sales -7.3% vs -0.5% expected", -7.3, -0.5, "forecast", "USD", False, -1),
    ("US September housing starts 1.221M vs 1.305M", 1.221, 1.305, "forecast", "USD", False, -1),
    ("Germany October ZEW survey current conditions -35.9 vs -45.0 expected", -35.9, -45.0, "forecast", "EUR", False, 1),
    ("Germany September PPI +1.9% vs +1.5% m/m expected", 1.9, 1.5, "forecast", "EUR", False, 1),
    ("Canada September CPI 3.1% y/y vs 3.2% expected", 3.1, 3.2, "forecast", "CAD", False, -1),
    ("US NAHB housing market index 29 vs 31 prior", 29, 31, "prior", "USD", False, -1),
    ("US retails sales for September 0.8% MoM vs 0.3% estimate. Prior month 1.3%", 0.8, 0.3, "forecast", "USD", False, 1),
    ("US September non-farm payrolls +29K vs +90K expected", 29, 90, "forecast", "USD", False, -1),
    ("US International Trade balance for August -105.6B vs -102.0B.", -105.6, -102.0, "forecast", "USD", False, -1),
    ("Canada August trade balance $4.20 billion vs $1.55 billion expected", 4.20, 1.55, "forecast", "CAD", False, 1),
    ("UK September final services PMI 52.1 vs 51.7 prelim", 52.1, 51.7, "prior", "GBP", False, 1),
    ("US GDP Final for Q2 2.2% vs 1.5% estimate", 2.2, 1.5, "forecast", "USD", False, 1),
    ("US July core PCE 3.0% y/y vs 3.3% expected", 3.0, 3.3, "forecast", "USD", False, -1),
    ("US initial jobless claims for the week is modestly stronger at 197K vs 200K est.", 197, 200, "forecast", "USD", True, 1),
    ("Eurozone September final CPI +3.8% vs +3.8% y/y prelim", 3.8, 3.8, "prior", "EUR", False, 0),
    ("US advance goods trade balance for August -$132.6 billion vs -$115.00 billion expected", -132.6, -115.0, "forecast", "USD", False, -1),
]


@pytest.mark.parametrize("title,actual,cmp,kind,ccy,inverse,strength", CASES)
def test_parse_real_titles(title, actual, cmp, kind, ccy, inverse, strength):
    r = parse_release(title)
    assert r is not None, title
    assert (r.actual, r.compare, r.kind, r.currency, r.inverse, r.strength) == (actual, cmp, kind, ccy, inverse, strength), title


@pytest.mark.parametrize("title", [
    "A breakthrough in US-Iran negotiations is expected to be announced this week, according to Al-Arabiya",
    "Fed's Powell: rates are in a good place",
    "Gold climbs to record as dollar slips",
])
def test_non_release_titles_ignored(title):
    assert parse_release(title) is None


def test_context_mentions_inverse_and_verdict():
    c = release_context("US initial jobless claims 194K vs 200K estimate")
    assert "inverse" in c and "STRONGER" in c and "USD" in c
    assert release_context("US NAHB housing market index 29 vs 31 prior") is None   # prior ≠ forecast


from app.services.release_parser import format_actual, match_release  # noqa: E402

IL = [
    "US initial jobless claims 194K vs 200K estimate. Better than expected.",
    "US retails sales for September 0.8% MoM vs 0.3% estimate. Prior month 1.3%",
    "US September non-farm payrolls +29K vs +90K expected",
    "US October UMich prelim consumer sentiment 46.3 vs 47.8 expected",
    "US September ISM manufacturing 54.5 vs 55.0 expected",
    "Germany September PPI +1.9% vs +1.5% m/m expected",
    "Canada September CPI 3.1% y/y vs 3.2% expected",
]
CANDS = [(t, parse_release(t)) for t in IL]


@pytest.mark.parametrize("ff_title,ccy,expect_actual", [
    ("Unemployment Claims", "USD", 194),
    ("Retail Sales m/m", "USD", 0.8),
    ("Non-Farm Employment Change", "USD", 29),
    ("Prelim UoM Consumer Sentiment", "USD", 46.3),
    ("ISM Manufacturing PMI", "USD", 54.5),
    ("German PPI m/m", "EUR", 1.9),
])
def test_match_calendar_event_to_release(ff_title, ccy, expect_actual):
    r = match_release(ff_title, ccy, CANDS)
    assert r is not None and r.actual == expect_actual, ff_title


@pytest.mark.parametrize("ff_title,ccy", [
    ("Unemployment Claims", "EUR"),          # jiná měna
    ("Core CPI m/m", "USD"),                 # nic odpovídajícího
    ("German PPI y/y", "EUR"),               # jiné období (m/m ≠ y/y)
    ("Building Permits", "USD"),
])
def test_no_false_matches(ff_title, ccy):
    assert match_release(ff_title, ccy, CANDS) is None


def test_format_actual_like_forecast():
    assert format_actual(parse_release(IL[0]), "200K") == "194K"
    assert format_actual(parse_release(IL[1]), "0.3%") == "0.8%"


@pytest.mark.parametrize("title,cat,ccy", [
    ("US July core PCE 3.0% y/y vs 3.3% expected", "inflation", "USD"),
    ("US September non-farm payrolls +29K vs +90K expected", "labor", "USD"),
    ("JOLTS job openings 7.079M vs 7.225M estimate", "labor", "USD"),
    ("September final UMich consumer sentiment 48.1 vs 47.6 expected", "growth", "USD"),
    ("US July CaseShiller 20-city house price index +2.5% vs 2.2% expected", "growth", "USD"),
    ("US September ISM manufacturing 54.5 vs 55.0 expected", "growth", "USD"),
])
def test_category_and_us_only_indicators(title, cat, ccy):
    r = parse_release(title)
    assert (r.category, r.currency) == (cat, ccy)
    assert f"[{cat} data]" in release_context(title)
