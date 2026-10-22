"""Měření reakce: cena PŘED zprávou (svíčka končící v čase zprávy) a kotva na čas vydání dat."""
from datetime import datetime, timezone

from app.services.release_parser import release_anchor
from app.sources.yahoo_finance_adapter import _close_before

T0 = datetime(2026, 10, 15, 12, 30, tzinfo=timezone.utc)
ts = int(T0.timestamp())
# svíčka 12:25–12:30 close 100 (před vydáním), 12:30–12:35 close 105 (skok po vydání)
BARS = [{"t": ts - 600, "close": 99.0}, {"t": ts - 300, "close": 100.0}, {"t": ts, "close": 105.0},
        {"t": ts + 300, "close": 106.0}]


def test_price_before_news_excludes_first_reaction_bar():
    assert _close_before(BARS, T0) == 100.0                       # ne 105 (to už je po zprávě)
    assert _close_before(BARS, T0.replace(minute=35)) == 105.0     # cena platná v 12:35


def test_close_before_respects_tolerance():
    assert _close_before(BARS, T0.replace(hour=14), tolerance_minutes=10) is None


def test_release_anchor_snaps_to_scheduled_time():
    pub = datetime(2026, 10, 15, 12, 36, tzinfo=timezone.utc)
    assert release_anchor("US initial jobless claim 199K vs 200K estimate", pub) == T0
    # běžná zpráva / prior / příliš pozdě po čtvrthodině → čas publikace
    assert release_anchor("Gold climbs as dollar slips", pub) == pub
    assert release_anchor("US NAHB housing market index 29 vs 31 prior", pub) == pub
    late = datetime(2026, 10, 15, 12, 41, tzinfo=timezone.utc)
    assert release_anchor("US retail sales 0.8% vs 0.3% expected", late) == late
