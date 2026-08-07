"""Peer z-score v rámci skupiny — medián + MAD (robustní), winsorize ±3.

Průměr a směrodatná odchylka záměrně NE: jedna extrémní firma by rozhodila
celou skupinu. Viz sekce 6 specu.
"""
from __future__ import annotations

import statistics

WINSOR = 3.0


def _median(xs: list[float]) -> float:
    return statistics.median(xs)


def _mad(xs: list[float], med: float) -> float:
    return statistics.median([abs(x - med) for x in xs])


def peer_zscores(values: dict[str, float | None]) -> dict[str, float | None]:
    """Vrátí z-score per ticker. Potřeba ≥5 nenulových hodnot ve skupině."""
    present = {t: v for t, v in values.items() if v is not None}
    out: dict[str, float | None] = {t: None for t in values}
    if len(present) < 5:
        return out
    xs = list(present.values())
    med = _median(xs)
    mad = _mad(xs, med)
    if mad == 0:
        return out
    for t, v in present.items():
        z = (v - med) / mad
        out[t] = round(max(-WINSOR, min(WINSOR, z)), 3)
    return out
