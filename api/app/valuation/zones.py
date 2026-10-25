"""Rozhodovací zóny Valuation Radaru: kde je firma „k prověření nákupu“, „držet“ a „spíše nepřikupovat“.

Zóna se počítá ze stejných dvou veličin, jaké má bublinová mapa:
  X = percentil forward P/E vůči VLASTNÍ historii firmy (0 = historicky nejlevnější, 100 = nejdražší)
  Y = očekávaný růst EPS na 12 měsíců (bez odhadů trailing růst)
a ze stejné škály růstu, jakou používá skóre růstu (scoring_config.PIECEWISE["eps_growth_ntm"]):

  zone_score = 0.5 × (100 − percentil) + 0.5 × skóre_růstu(Y)      (0–100)
  ≥ ZONE_BUY  → „buy“   (levná vůči sobě a/nebo silně rostoucí: k prověření nákupu)
  ≥ ZONE_SELL → „hold“  (držet / sledovat)
  jinak       → „avoid“ (drahá vůči růstu: spíše nepřikupovat, zvážit prodej)

Princip „růst za rozumnou cenu“ (GARP): čím dražší vůči své historii, tím vyšší růst musí ospravedlnit cenu.
NENÍ to ověřeno historickou výnosností (skóre se sbírá teprve od 8/2026) — jen orientační pravidlo.
"""
from __future__ import annotations

from app.valuation import scoring_config as C
from app.valuation.scoring import piecewise

ZONE_BUY = 60.0
ZONE_SELL = 40.0
_GROWTH = C.PIECEWISE["eps_growth_ntm"]


def zone_score(pctile: float | None, growth: float | None) -> float | None:
    if pctile is None or growth is None:
        return None
    return round(0.5 * (100.0 - max(0.0, min(100.0, pctile))) + 0.5 * piecewise(growth, _GROWTH), 2)


def zone(pctile: float | None, growth: float | None) -> str | None:
    s = zone_score(pctile, growth)
    if s is None:
        return None
    return "buy" if s >= ZONE_BUY else "hold" if s >= ZONE_SELL else "avoid"


def _growth_for_subscore(target: float) -> float | None:
    """Inverze po částech lineární škály růstu: jaký růst dá dané subskóre (None = nedosažitelné)."""
    if target > _GROWTH[-1][1]:
        return None
    if target <= _GROWTH[0][1]:
        return float(_GROWTH[0][0])
    for (x0, y0), (x1, y1) in zip(_GROWTH, _GROWTH[1:]):
        if y0 <= target <= y1:
            return round(x0 + (target - y0) / (y1 - y0) * (x1 - x0), 2)
    return None


def boundary(threshold: float, step: int = 5) -> list[list[float]]:
    """Body křivky [percentil, růst], kde zone_score = threshold. Kde je hranice nedosažitelná, bod chybí."""
    pts = []
    for p in range(0, 101, step):
        g = _growth_for_subscore(2 * threshold - (100 - p))
        if g is not None:
            pts.append([float(p), g])
    return pts


def zone_curves() -> dict:
    return {"buy": boundary(ZONE_BUY), "sell": boundary(ZONE_SELL),
            "buy_threshold": ZONE_BUY, "sell_threshold": ZONE_SELL}
