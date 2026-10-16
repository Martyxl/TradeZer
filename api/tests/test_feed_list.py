"""Konfigurace RSS zdrojů: bez duplicit, platné URL, žádné známé mrtvé feedy (ověřeno živou zkouškou
z Vercelu 2026-10-16: Reuters zanikl, FXStreet 403)."""
from urllib.parse import urlparse

from app.sources.rss_adapter import DEFAULT_FEEDS, build_default_rss_adapters

DEAD_HOSTS = {"feeds.reuters.com", "www.fxstreet.com", "fxstreet.com"}
VALID_TICKERS = {"NQ", "ES", "YM", "XAUUSD"}


def test_names_and_urls_are_unique_and_valid():
    names = [f["name"] for f in DEFAULT_FEEDS]
    urls = [f["url"] for f in DEFAULT_FEEDS]
    assert len(names) == len(set(names)) and len(urls) == len(set(urls))
    for f in DEFAULT_FEEDS:
        assert f["name"].startswith("rss_") and urlparse(f["url"]).scheme == "https", f
        assert 0 < f["source_weight"] <= 1, f


def test_no_known_dead_feeds():
    for f in DEFAULT_FEEDS:
        assert urlparse(f["url"]).hostname not in DEAD_HOSTS, f"mrtvý zdroj: {f['name']}"


def test_hints_are_tracked_instruments_only():
    for f in DEFAULT_FEEDS:
        assert set(f["instruments_hint"]) <= VALID_TICKERS, f   # EURUSD/BTCUSD se nesledují


def test_central_bank_feeds_cover_all_instruments_and_adapters_build():
    by = {f["name"]: f for f in DEFAULT_FEEDS}
    assert set(by["rss_fed_press"]["instruments_hint"]) == VALID_TICKERS
    assert set(by["rss_fed_speeches"]["instruments_hint"]) == VALID_TICKERS
    assert len(build_default_rss_adapters()) == len(DEFAULT_FEEDS)
