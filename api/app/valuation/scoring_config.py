"""Konfigurace skórování — VŠECHNY prahy a váhy na jednom místě (žádné magic numbers jinde).

Změna vah/vzorce = inkrement VAL_MODEL_VERSION (stará skóre se nepřepočítávají).
"""

# ---- Váhy komponent v composite ---------------------------------------------
COMPOSITE_WEIGHTS = {
    "valuation": 0.35,
    "growth": 0.25,
    "quality": 0.20,
    "revision": 0.15,
    "trend": 0.05,
}

# ---- Váhy vstupů uvnitř komponent -------------------------------------------
VALUATION_WEIGHTS = {
    "pctile_pe_fwd": 0.35,      # invertovaný percentil
    "pctile_ev_ebitda": 0.25,   # invertovaný percentil
    "z_pe_fwd": 0.20,           # invertovaný peer z-score
    "peg_fwd": 0.20,            # pásmo
}
GROWTH_WEIGHTS = {
    "eps_growth_ntm": 0.40,
    "revenue_growth_ntm": 0.30,
    "revenue_yoy_ttm": 0.20,
    "growth_accel": 0.10,
}
QUALITY_WEIGHTS = {
    "roic": 0.30,
    "fcf_margin": 0.25,
    "net_debt_to_ebitda": 0.20,   # invertovaný
    "margin_trend": 0.15,
    "share_count_change": 0.10,   # invertovaný
}
REVISION_WEIGHTS = {
    "revision_ratio_30d": 0.45,
    "estimate_drift_90d": 0.35,
    "avg_surprise_4q": 0.20,
}
TREND_WEIGHTS = {
    "px_vs_sma200": 0.50,
    "mom_12_1": 0.30,
    "max_dd_1y": 0.20,            # invertovaný
}

# ---- Po částech lineární škály: [(hodnota, subskóre), ...] vzestupně ---------
PIECEWISE = {
    "eps_growth_ntm":     [(-20, 0), (0, 25), (10, 50), (20, 75), (40, 100)],
    "revenue_growth_ntm": [(-10, 0), (0, 30), (8, 55), (15, 80), (30, 100)],
    "revenue_yoy_ttm":    [(-10, 0), (0, 30), (8, 55), (15, 80), (30, 100)],
    "growth_accel":       [(-15, 0), (-5, 30), (0, 50), (5, 75), (15, 100)],
    "roic":               [(0, 0), (8, 40), (15, 65), (25, 90), (40, 100)],
    "fcf_margin":         [(0, 0), (8, 45), (18, 75), (30, 100)],
    "net_debt_to_ebitda": [(-1, 100), (0, 90), (1, 75), (2, 55), (3, 35), (4, 15), (6, 0)],  # invertovaný smysl už v datech
    "margin_trend":       [(-5, 0), (-1, 35), (0, 50), (2, 75), (5, 100)],
    "share_count_change": [(-5, 100), (-1, 80), (0, 60), (2, 35), (5, 10), (10, 0)],
    "px_vs_sma200":       [(-20, 0), (-5, 35), (0, 50), (10, 80), (25, 100)],
    "mom_12_1":           [(-30, 0), (-10, 25), (0, 45), (20, 80), (50, 100)],
    "max_dd_1y":          [(-60, 0), (-40, 25), (-25, 50), (-12, 75), (0, 100)],
    "avg_surprise_4q":    [(-15, 0), (-5, 30), (0, 50), (5, 75), (15, 100)],
    "estimate_drift_90d": [(-0.15, 0), (-0.05, 30), (0, 50), (0.05, 75), (0.15, 100)],
    "revision_ratio_30d": [(-1, 0), (-0.3, 30), (0, 50), (0.3, 75), (1, 100)],
}

# ---- PEG pásmo (nižší = levnější = vyšší subskóre) ---------------------------
PEG_BANDS = [(1.0, 100), (1.5, 75), (2.0, 50), (3.0, 25)]  # nad 3.0 → 0
PEG_ABOVE = 0

# ---- Verdikty ---------------------------------------------------------------
VALUATION_VERDICTS = [(70, "LEVNÁ"), (55, "FÉROVÁ"), (40, "NAPJATÁ"), (0, "PŘEPÁLENÁ")]
HORIZON_VERDICTS = [(70, "VHODNÁ K DRŽBĚ"), (55, "SPÍŠE ANO"), (40, "NEUTRÁLNÍ"), (0, "SPÍŠE NE")]

# ---- Bubble flag ------------------------------------------------------------
BUBBLE = {"pctile_pe_fwd_gt": 85, "growth_accel_lt": 0, "revision_ratio_lt": 0}

# ---- Confidence -------------------------------------------------------------
CONF_ANALYSTS_FULL = 15   # min(n_analysts/15, 1)
CONF_YEARS_FULL = 5       # min(years/5, 1)
CONF_UNRELIABLE = 0.5     # pod tímto prahem = nespolehlivé
CONF_NO_ESTIMATES = 0.6   # faktor když zdroj odhady nedodává (n_analysts None)

# invertované vstupy (percentily/z: vysoká hodnota = drahé = nízké subskóre)
INVERTED_PERCENTILES = {"pctile_pe_fwd", "pctile_ev_ebitda"}
INVERTED_ZSCORES = {"z_pe_fwd"}
