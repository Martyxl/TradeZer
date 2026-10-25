"""Rozhodovací zóny Valuation Radaru (GARP: čím dražší vůči historii, tím vyšší růst je potřeba)."""
import pytest

from app.valuation.zones import ZONE_BUY, ZONE_SELL, boundary, zone, zone_curves, zone_score


@pytest.mark.parametrize("p,g,expected", [
    (10, 15, "buy"),     # levná vůči historii + slušný růst
    (40, 14, "buy"),     # přesně na hranici nákupu
    (60, 15, "hold"),    # dražší, růst nestačí na nákup
    (85, 50, "hold"),    # nad 80. percentilem nikdy nákup
    (90, 5, "avoid"),    # drahá a pomalá
    (60, 0, "avoid"),
    (None, 10, None), (50, None, None),
])
def test_zone_classification(p, g, expected):
    assert zone(p, g) == expected


def test_boundaries_match_thresholds_and_are_monotonic():
    for thr, curve in ((ZONE_BUY, boundary(ZONE_BUY)), (ZONE_SELL, boundary(ZONE_SELL))):
        growth = [g for _, g in curve]
        assert growth == sorted(growth)                       # dražší → potřeba vyššího růstu
        for p, g in curve:
            if g > -20:                                       # mimo dolní klemp škály
                assert abs(zone_score(p, g) - thr) < 0.6
    buy = dict((p, g) for p, g in boundary(ZONE_BUY))
    assert buy[0] == -4 and buy[40] == 14 and buy[80] == 40 and 85 not in buy


def test_curves_payload():
    c = zone_curves()
    assert c["buy_threshold"] == 60 and c["sell_threshold"] == 40 and c["buy"] and c["sell"]
