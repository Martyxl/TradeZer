"""Testy deterministického outlook rule enginu (offline)."""
from app.services.outlook_service import (
    classify_event, scenario_for, _realized_bucket, _parse_event_values,
)


def test_parse_event_values_from_body():
    body = "Status: RELEASED\nCurrency: USD\nImpact: high\nActual: 0.4%\nForecast: 0.3%\nPrevious: 0.2%"
    assert _parse_event_values(body, "") == ("0.3%", "0.4%")
    # z titulku, chybějící actual → None
    title = "[USD] Core PPI m/m ⚡ HIGH IMPACT | Upcoming | Forecast: 0.3% | Prev: 0.2%"
    fc, ac = _parse_event_values("", title)
    assert fc == "0.3%" and ac is None


def test_classify_inflation_and_claims():
    assert classify_event("Core PPI m/m") == "inflation"
    assert classify_event("CPI y/y") == "inflation"
    assert classify_event("Unemployment Claims") == "claims"
    assert classify_event("Non-Farm Employment Change") == "jobs"
    assert classify_event("Retail Sales m/m") == "growth"
    assert classify_event("FOMC Statement") == "rates"
    assert classify_event("Něco úplně jiného") is None


def test_inflation_hot_pushes_indices_and_gold_down():
    sc = scenario_for("inflation", "NQ")
    assert sc["hot"]["dir"] == "down"      # hot inflace → indexy dolů
    assert sc["cool"]["dir"] == "up"       # cool inflace → indexy nahoru
    assert sc["inline"]["dir"] == "flat"
    gold = scenario_for("inflation", "XAUUSD")
    assert gold["hot"]["dir"] == "down"    # hot inflace → silnější dolar/yieldy → gold dolů


def test_claims_is_inverse():
    # více žádostí (hot) = slabší trh práce = holubičí = risk-on nahoru
    sc = scenario_for("claims", "ES")
    assert sc["hot"]["dir"] == "up"
    assert sc["cool"]["dir"] == "down"


def test_nq_more_sensitive_note():
    assert "tech" in scenario_for("inflation", "NQ")["hot"]["text"]
    assert "tech" not in scenario_for("inflation", "YM")["hot"]["text"]


def test_unknown_category_returns_none():
    assert scenario_for("nonsense", "NQ") is None


def test_realized_bucket():
    assert _realized_bucket("0.5%", "0.3%") == "hot"
    assert _realized_bucket("0.1%", "0.3%") == "cool"
    assert _realized_bucket("0.3%", "0.3%") == "inline"
    assert _realized_bucket("", "0.3%") is None
    assert _realized_bucket("230K", "199K") == "hot"      # ~15 % nad = hot
    assert _realized_bucket("202K", "199K") == "inline"   # ~1.5 % = v toleranci
