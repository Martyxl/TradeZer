"""Geopolitické zprávy musí projít klíčovým filtrem (dřív se zahazovaly)."""
from types import SimpleNamespace

from app.services.news_aggregator import _detect_tickers_by_keywords, is_geopolitical

TICKERS = [SimpleNamespace(symbol=s) for s in ("XAUUSD", "NQ", "ES", "YM", "EURUSD")]


def syms(title, body=None):
    return {t.symbol for t in _detect_tickers_by_keywords(title, body, TICKERS)}


def test_china_israel_nuclear_threat_reaches_safe_haven_and_indices():
    s = syms("China warns Israel will vanish if it uses nuclear weapons against Iran")
    assert {"XAUUSD", "NQ", "ES", "YM"} <= s
    assert "EURUSD" not in s


def test_hormuz_oil_missile_headlines():
    assert "XAUUSD" in syms("Missile strike near Strait of Hormuz sends Brent higher")
    assert "NQ" in syms("OPEC+ surprise cut lifts crude")


def test_word_boundary_no_false_positive_on_fed_governor_miran():
    assert not is_geopolitical("Fed governor Miran says rates should fall")
    assert not syms("Fed governor Miran says rates should fall")


def test_regular_news_unchanged():
    assert syms("Gold price rallies after weak payrolls") == {"XAUUSD"}
    assert syms("Local bakery opens new store") == set()
