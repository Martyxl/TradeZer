"""Skórovací engine — čistý, izolovaný, bez I/O (sekce 7 specu).

Vstup = metriky (dict) + n_analysts + roky historie. Výstup = ScoreResult.
Chybějící vstup → komponenta se vyřadí, váhy se přenormalizují, confidence klesne.
Nikdy neimputuje. Prahy výhradně z scoring_config.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.valuation import scoring_config as C


# ---- normalizační helpery ---------------------------------------------------

def piecewise(value: float | None, points: list[tuple[float, float]]) -> float | None:
    """Lineární interpolace mezi body [(x, subskóre)], klemp na okraje."""
    if value is None:
        return None
    if value <= points[0][0]:
        return float(points[0][1])
    if value >= points[-1][0]:
        return float(points[-1][1])
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= value <= x1:
            t = (value - x0) / (x1 - x0) if x1 != x0 else 0
            return round(y0 + t * (y1 - y0), 2)
    return float(points[-1][1])


def invert_percentile(p: float | None) -> float | None:
    return None if p is None else 100.0 - p


def invert_zscore(z: float | None) -> float | None:
    """z ∈ [-3,3]: -3 (levné) → 100, +3 (drahé) → 0, 0 → 50."""
    if z is None:
        return None
    return round(max(0.0, min(100.0, (3.0 - z) / 6.0 * 100.0)), 2)


def peg_subscore(peg: float | None) -> float | None:
    if peg is None:
        return None
    for threshold, score in C.PEG_BANDS:
        if peg < threshold:
            return float(score)
    return float(C.PEG_ABOVE)


def _subscore(name: str, value: float | None) -> float | None:
    """Převede surovou metriku na subskóre 0–100 podle jejího typu."""
    if value is None:
        return None
    if name in C.INVERTED_PERCENTILES:
        return invert_percentile(value)
    if name in C.INVERTED_ZSCORES:
        return invert_zscore(value)
    if name == "peg_fwd":
        return peg_subscore(value)
    if name in C.PIECEWISE:
        return piecewise(value, C.PIECEWISE[name])
    return None


# ---- komponenta -------------------------------------------------------------

@dataclass
class _Contribution:
    name: str
    raw: float | None
    subscore: float | None
    weight: float          # efektivní váha v composite (po renormalizaci)
    points: float          # (subscore-50) * weight → příspěvek k odklonu


def _component(metrics: dict, weights: dict[str, float]) -> tuple[float | None, dict, int, int]:
    """Vrátí (skóre, {name: subscore}, n_present, n_total) s renormalizací vah."""
    subs, present_w = {}, {}
    for name, w in weights.items():
        s = _subscore(name, metrics.get(name))
        subs[name] = s
        if s is not None:
            present_w[name] = w
    if not present_w:
        return None, subs, 0, len(weights)
    total_w = sum(present_w.values())
    score = sum(subs[n] * (w / total_w) for n, w in present_w.items())
    return round(score, 2), subs, len(present_w), len(weights)


def _verdict(score: float | None, bands: list[tuple[float, str]]) -> str | None:
    if score is None:
        return None
    for threshold, label in bands:
        if score >= threshold:
            return label
    return bands[-1][1]


# ---- výsledek ---------------------------------------------------------------

@dataclass
class ScoreResult:
    valuation_score: float | None = None
    growth_score: float | None = None
    quality_score: float | None = None
    revision_score: float | None = None
    trend_score: float | None = None
    composite_score: float | None = None
    valuation_verdict: str | None = None
    horizon_verdict: str | None = None
    bubble_flag: bool = False
    confidence: float | None = None
    drivers: dict = field(default_factory=lambda: {"positive": [], "negative": []})

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)


_COMPONENTS = [
    ("valuation", C.VALUATION_WEIGHTS),
    ("growth", C.GROWTH_WEIGHTS),
    ("quality", C.QUALITY_WEIGHTS),
    ("revision", C.REVISION_WEIGHTS),
    ("trend", C.TREND_WEIGHTS),
]

_LABEL_CS = {
    "pctile_pe_fwd": "P/E fwd vs. historie", "pctile_ev_ebitda": "EV/EBITDA vs. historie",
    "z_pe_fwd": "P/E fwd vs. sektor", "peg_fwd": "PEG", "eps_growth_ntm": "růst EPS (NTM)",
    "revenue_growth_ntm": "růst tržeb (NTM)", "revenue_yoy_ttm": "růst tržeb (TTM)",
    "growth_accel": "akcelerace růstu", "roic": "ROIC", "fcf_margin": "FCF marže",
    "net_debt_to_ebitda": "zadlužení", "margin_trend": "trend marží",
    "share_count_change": "změna počtu akcií", "revision_ratio_30d": "revize odhadů",
    "estimate_drift_90d": "drift odhadů 90d", "avg_surprise_4q": "překvapení (4Q)",
    "px_vs_sma200": "cena vs. SMA200", "mom_12_1": "momentum 12-1", "max_dd_1y": "max drawdown",
}


def score_metrics(metrics: dict, n_analysts: int | None = None,
                  years_history: float | None = None) -> ScoreResult:
    res = ScoreResult()
    comp_scores: dict[str, float | None] = {}
    all_subs: dict[str, dict] = {}
    total_present = total_inputs = 0

    for name, weights in _COMPONENTS:
        score, subs, n_present, n_total = _component(metrics, weights)
        comp_scores[name] = score
        all_subs[name] = subs
        total_present += n_present
        total_inputs += n_total

    res.valuation_score = comp_scores["valuation"]
    res.growth_score = comp_scores["growth"]
    res.quality_score = comp_scores["quality"]
    res.revision_score = comp_scores["revision"]
    res.trend_score = comp_scores["trend"]

    # composite s renormalizací vah přes přítomné komponenty
    present = {k: v for k, v in comp_scores.items() if v is not None}
    if present:
        w = {k: C.COMPOSITE_WEIGHTS[k] for k in present}
        tw = sum(w.values())
        res.composite_score = round(sum(present[k] * (w[k] / tw) for k in present), 2)

    res.valuation_verdict = _verdict(res.valuation_score, C.VALUATION_VERDICTS)
    res.horizon_verdict = _verdict(res.composite_score, C.HORIZON_VERDICTS)

    # bubble flag
    pe = metrics.get("pctile_pe_fwd")
    ga = metrics.get("growth_accel")
    rr = metrics.get("revision_ratio_30d")
    res.bubble_flag = (
        pe is not None and ga is not None and rr is not None
        and pe > C.BUBBLE["pctile_pe_fwd_gt"]
        and ga < C.BUBBLE["growth_accel_lt"]
        and rr < C.BUBBLE["revision_ratio_lt"]
    )

    # confidence = pokrytí metrik × pokrytí analytiky × délka historie
    fill = total_present / total_inputs if total_inputs else 0.0
    an = min((n_analysts or 0) / C.CONF_ANALYSTS_FULL, 1.0)
    yr = min((years_history or 0) / C.CONF_YEARS_FULL, 1.0)
    res.confidence = round(fill * an * yr, 3)

    # drivers: top 3 +/- podle příspěvku (subscore-50) × efektivní váha v composite
    contribs: list[_Contribution] = []
    for name, weights in _COMPONENTS:
        cw = C.COMPOSITE_WEIGHTS[name]
        subs = all_subs[name]
        present_inputs = {n: weights[n] for n in weights if subs[n] is not None}
        tw = sum(present_inputs.values()) or 1.0
        for n, w in present_inputs.items():
            eff = cw * (w / tw)
            pts = (subs[n] - 50.0) * eff
            contribs.append(_Contribution(
                name=_LABEL_CS.get(n, n), raw=metrics.get(n), subscore=subs[n],
                weight=round(eff, 4), points=round(pts, 3)))
    contribs.sort(key=lambda c: c.points, reverse=True)
    pos = [c for c in contribs if c.points > 0][:3]
    neg = [c for c in contribs if c.points < 0][-3:][::-1]
    res.drivers = {
        "positive": [{"name": c.name, "value": c.raw, "contribution": c.points} for c in pos],
        "negative": [{"name": c.name, "value": c.raw, "contribution": c.points} for c in neg],
    }
    return res
