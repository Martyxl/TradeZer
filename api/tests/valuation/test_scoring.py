"""P3 testy — skórovací engine (čistý, bez I/O)."""
import pytest

from app.valuation import scoring
from app.valuation.scoring import score_metrics, piecewise, invert_zscore, peg_subscore


def _full_metrics(**over) -> dict:
    m = dict(
        pctile_pe_fwd=50, pctile_ev_ebitda=50, z_pe_fwd=0.0, peg_fwd=1.4,
        eps_growth_ntm=15, revenue_growth_ntm=10, revenue_yoy_ttm=10, growth_accel=2,
        roic=18, fcf_margin=15, net_debt_to_ebitda=1.0, margin_trend=1, share_count_change=-1,
        revision_ratio_30d=0.2, estimate_drift_90d=0.03, avg_surprise_4q=3,
        px_vs_sma200=5, mom_12_1=12, max_dd_1y=-15,
    )
    m.update(over)
    return m


# ---- normalizační helpery ---------------------------------------------------

def test_piecewise_clamps_and_interpolates():
    pts = [(0, 0), (10, 50), (20, 100)]
    assert piecewise(-5, pts) == 0
    assert piecewise(25, pts) == 100
    assert piecewise(5, pts) == 25
    assert piecewise(None, pts) is None


def test_invert_zscore_bounds():
    assert invert_zscore(-3) == 100
    assert invert_zscore(3) == 0
    assert invert_zscore(0) == 50


def test_peg_bands():
    assert peg_subscore(0.9) == 100
    assert peg_subscore(1.4) == 75
    assert peg_subscore(2.5) == 25
    assert peg_subscore(4.0) == 0


# ---- property: skóre v 0–100 ------------------------------------------------

def test_all_scores_in_range():
    r = score_metrics(_full_metrics(), n_analysts=20, years_history=5)
    for s in (r.valuation_score, r.growth_score, r.quality_score,
              r.revision_score, r.trend_score, r.composite_score):
        assert s is None or 0 <= s <= 100


# ---- property: monotonie valuace v pctile_pe_fwd ----------------------------

def test_valuation_monotonic_in_pe_percentile():
    cheap = score_metrics(_full_metrics(pctile_pe_fwd=10), 20, 5).valuation_score
    mid = score_metrics(_full_metrics(pctile_pe_fwd=50), 20, 5).valuation_score
    exp = score_metrics(_full_metrics(pctile_pe_fwd=95), 20, 5).valuation_score
    assert cheap > mid > exp   # dražší (vyšší percentil) → nižší valuation score


# ---- confidence -------------------------------------------------------------

def test_confidence_drops_with_missing_and_few_analysts():
    full = score_metrics(_full_metrics(), n_analysts=20, years_history=5).confidence
    few = score_metrics(_full_metrics(), n_analysts=3, years_history=5).confidence
    sparse = score_metrics({"pe_ttm": 20}, n_analysts=20, years_history=5).confidence
    assert full > few          # méně analytiků → nižší confidence
    assert full > sparse       # méně vyplněných metrik → nižší confidence
    assert 0 <= sparse <= 1


def test_missing_inputs_never_raise():
    r = score_metrics({}, n_analysts=None, years_history=None)
    assert r.composite_score is None
    assert r.confidence == 0.0


# ---- bubble flag ------------------------------------------------------------

def test_bubble_flag_true():
    r = score_metrics(_full_metrics(pctile_pe_fwd=90, growth_accel=-5, revision_ratio_30d=-0.3), 20, 5)
    assert r.bubble_flag is True


def test_bubble_flag_needs_all_three():
    # drahé, ale růst zrychluje → není bublina
    r = score_metrics(_full_metrics(pctile_pe_fwd=95, growth_accel=5, revision_ratio_30d=0.4), 20, 5)
    assert r.bubble_flag is False


# ---- verdikty ---------------------------------------------------------------

def test_valuation_verdict_bands():
    assert score_metrics(_full_metrics(pctile_pe_fwd=5, z_pe_fwd=-3, peg_fwd=0.8), 20, 5).valuation_verdict == "LEVNÁ"
    assert score_metrics(_full_metrics(pctile_pe_fwd=98, z_pe_fwd=3, peg_fwd=5), 20, 5).valuation_verdict == "PŘEPÁLENÁ"


# ---- drivers ----------------------------------------------------------------

def test_drivers_present_and_ranked():
    r = score_metrics(_full_metrics(eps_growth_ntm=40, roic=40, pctile_pe_fwd=95), 20, 5)
    assert len(r.drivers["positive"]) <= 3
    assert len(r.drivers["negative"]) <= 3
    # nejlepší pozitivní má vyšší příspěvek než druhý
    pos = r.drivers["positive"]
    if len(pos) >= 2:
        assert pos[0]["contribution"] >= pos[1]["contribution"]


# ---- renormalizace vah při chybějícím vstupu --------------------------------

def test_component_renormalizes_on_missing():
    # jen jeden vstup valuace přítomen → skóre = jeho subskóre
    r = score_metrics({"pctile_pe_fwd": 20}, 20, 5)
    assert r.valuation_score == 80.0   # invert(20) = 80, renormalizováno na 100 % váhy
