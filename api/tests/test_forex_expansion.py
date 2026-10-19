"""Rozšíření o forex páry EURUSD / GBPUSD / USDJPY: hinty z kalendáře, klíčová slova, scénáře outlooku."""
from types import SimpleNamespace

from app.services.news_aggregator import _detect_tickers_by_keywords
from app.services.outlook_service import build_outlook, scenario_for
from app.sources.forex_factory import ForexFactoryAdapter

T = [SimpleNamespace(symbol=s) for s in ("EURUSD", "GBPUSD", "USDJPY", "ES", "NQ", "YM", "XAUUSD")]


def syms(title, body=None):
    return {t.symbol for t in _detect_tickers_by_keywords(title, body, T)}


def test_calendar_hints_per_currency():
    a = ForexFactoryAdapter()
    assert a._instruments_hint("GBP") == ["GBPUSD"]
    assert a._instruments_hint("JPY") == ["USDJPY"]
    assert "EURUSD" in a._instruments_hint("EUR") and "GBPUSD" in a._instruments_hint("USD")
    assert a._instruments_hint("CHF") == []


def test_central_bank_keywords_hit_right_pair():
    assert syms("Bank of England holds rates, Bailey warns on inflation") >= {"GBPUSD"}
    assert "USDJPY" in syms("BOJ's Ueda signals further hikes as yen slides")
    assert "EURUSD" in syms("ECB's Lagarde says rates on hold")


def test_word_boundaries_avoid_false_positives():
    assert "GBPUSD" not in syms("Boeing shares fall after delivery halt")
    assert "GBPUSD" not in syms("Compound interest explained")
    assert "USDJPY" not in syms("The yenta gossiped at the market")


def test_us_macro_drives_all_usd_pairs():
    hit = syms("US nonfarm payrolls beat forecast, Fed rate cut bets fade")
    assert {"EURUSD", "GBPUSD", "USDJPY"} <= hit


def test_unrelated_news_hits_no_pair():
    assert not (syms("Local bakery wins award") & {"EURUSD", "GBPUSD", "USDJPY"})


def test_fx_scenarios_signs():
    # horká US inflace = silnější USD → EURUSD dolů, USDJPY nahoru
    assert scenario_for("inflation", "EURUSD", "USD")["hot"]["dir"] == "down"
    assert scenario_for("inflation", "GBPUSD", "USD")["hot"]["dir"] == "down"
    assert scenario_for("inflation", "USDJPY", "USD")["hot"]["dir"] == "up"
    # horká britská inflace = silnější GBP → GBPUSD nahoru; japonská → USDJPY dolů
    assert scenario_for("inflation", "GBPUSD", "GBP")["hot"]["dir"] == "up"
    assert scenario_for("inflation", "USDJPY", "JPY")["hot"]["dir"] == "down"
    # vyšší nezaměstnanost USD = slabší USD → EURUSD nahoru
    assert scenario_for("unemployment_rate", "EURUSD", "USD")["hot"]["dir"] == "up"
    # cool je opak hot
    assert scenario_for("inflation", "EURUSD", "USD")["cool"]["dir"] == "up"


def test_fx_ignores_foreign_currency_events_of_other_pairs():
    assert scenario_for("inflation", "EURUSD", "JPY") is None
    assert scenario_for("inflation", "USDJPY", "GBP") is None


def test_indices_and_gold_unchanged_and_ignore_gbp_jpy():
    assert scenario_for("inflation", "NQ", "USD")["hot"]["dir"] == "down"
    assert scenario_for("inflation", "XAUUSD", "USD")["hot"]["dir"] == "down"
    assert scenario_for("inflation", "NQ", "GBP") is None
    assert scenario_for("inflation", "XAUUSD", "JPY") is None
