"""Metriky Valuation Radaru — čisté funkce, žádné I/O (sekce 6 specu).

Vše deterministické. Chybějící vstup → None (nikdy neimputovat). TTM = součet
posledních 4 kvartálů; při chybě fallback na roční s poznámkou v `notes`.
Historické percentily a peer z-score jsou point-in-time (viz metrics_pit / peer.py).
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field, asdict
from datetime import date

TAX_RATE = 0.21


# ---- číselné helpery --------------------------------------------------------

def safe_div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _sum(vals: list[float | None]) -> float | None:
    present = [v for v in vals if v is not None]
    if not present:
        return None
    return sum(present)


def pct(a: float | None, b: float | None) -> float | None:
    """(a/b - 1) * 100."""
    r = safe_div(a, b)
    return None if r is None else (r - 1.0) * 100.0


# ---- TTM --------------------------------------------------------------------

def ttm(quarters: list[dict], field_name: str) -> float | None:
    """Součet posledních 4 kvartálů (quarters seřazené period_end DESC)."""
    vals = [q.get(field_name) for q in quarters[:4]]
    if len([v for v in vals if v is not None]) < 4:
        return None
    return _sum(vals)


def yoy_ttm(quarters: list[dict], field_name: str) -> float | None:
    """Meziroční změna TTM: (TTM_teď / TTM_před 4Q − 1)*100."""
    now = ttm(quarters[:4], field_name)
    prev = ttm(quarters[4:8], field_name)
    return pct(now, prev)


# ---- eps NTM (vážený mix current_y / next_y) --------------------------------

def eps_ntm(current_y: float | None, next_y: float | None,
            fy_end_month: int, today: date) -> float | None:
    if current_y is None and next_y is None:
        return None
    if current_y is None:
        return next_y
    if next_y is None:
        return current_y
    months_left = (fy_end_month - today.month) % 12
    w_current = months_left / 12.0
    return w_current * current_y + (1 - w_current) * next_y


# ---- základ + násobky -------------------------------------------------------

@dataclass
class MetricSet:
    ticker: str
    as_of_date: str
    # základ
    market_cap: float | None = None
    net_debt: float | None = None
    enterprise_value: float | None = None
    fcf_ttm: float | None = None
    # násobky
    pe_ttm: float | None = None
    pe_fwd: float | None = None
    ev_ebitda: float | None = None
    ev_sales: float | None = None
    p_fcf: float | None = None
    peg_fwd: float | None = None
    # percentily vůči vlastní historii (0–100)
    pctile_pe_ttm: float | None = None
    pctile_pe_fwd: float | None = None
    pctile_ev_ebitda: float | None = None
    # peer z-score (doplní peer.py)
    z_pe_fwd: float | None = None
    z_ev_ebitda: float | None = None
    # růst
    revenue_yoy_ttm: float | None = None
    eps_yoy_ttm: float | None = None
    revenue_growth_ntm: float | None = None
    eps_growth_ntm: float | None = None
    growth_accel: float | None = None
    # kvalita
    gross_margin: float | None = None
    operating_margin: float | None = None
    fcf_margin: float | None = None
    roic: float | None = None
    net_debt_to_ebitda: float | None = None
    margin_trend: float | None = None
    share_count_change: float | None = None
    # momentum odhadů
    revision_ratio_30d: float | None = None
    estimate_drift_90d: float | None = None
    avg_surprise_4q: float | None = None
    # trend a riziko
    px_vs_sma200: float | None = None
    mom_12_1: float | None = None
    max_dd_1y: float | None = None
    realized_vol_60d: float | None = None
    # meta
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ---- historické percentily (point-in-time) ----------------------------------

def _pit_ttm_eps(quarters: list[dict], as_of: date) -> float | None:
    """TTM EPS dostupné k datu as_of: 4 nejnovější Q s report_date <= as_of."""
    avail = [q for q in quarters if q.get("report_date") and q["report_date"] <= as_of]
    avail.sort(key=lambda q: q["period_end"], reverse=True)
    return ttm(avail, "eps_diluted")


def historical_pe_series(quarters: list[dict], prices: list[dict]) -> list[float]:
    """Denní řada pe_ttm za dostupnou historii (point-in-time TTM zisk)."""
    series = []
    for p in prices:
        close, d = p.get("close"), p.get("date")
        if close is None or d is None:
            continue
        eps = _pit_ttm_eps(quarters, d)
        if eps and eps > 0:
            series.append(close / eps)
    return series


def percentile_rank(series: list[float], value: float | None, min_points: int = 20) -> float | None:
    """V jakém percentilu (0–100) je `value` v `series`. min_points = minimální historie
    (na free datech ze SEC bývá mělká; nižší práh = víc firem má verdikt, slabší statistika)."""
    if value is None or len(series) < min_points:
        return None
    below = sum(1 for x in series if x <= value)
    return round(100.0 * below / len(series), 1)


# ---- hlavní výpočet single-ticker -------------------------------------------

def compute_metrics(
    ticker: str,
    as_of: date,
    close: float | None,
    quarters: list[dict],        # period_end DESC, s report_date jako date
    annual: list[dict],          # FY, period_end DESC
    estimates: dict,             # {(horizon,metric): {avg,...}}
    trend: dict,                 # {horizon: {current, days_ago_90,...}}
    surprises: list[float],      # surprise_pct posledních Q (nejnovější první)
    prices: list[dict],          # date ASC, {date, close}
    fy_end_month: int = 12,
) -> MetricSet:
    m = MetricSet(ticker=ticker, as_of_date=as_of.isoformat())

    eps_ttm_v = ttm(quarters, "eps_diluted")
    revenue_ttm = ttm(quarters, "revenue")
    ebitda_ttm = ttm(quarters, "ebitda")
    op_income_ttm = ttm(quarters, "operating_income")
    cfo_ttm = ttm(quarters, "cfo")
    capex_ttm = ttm(quarters, "capex")
    gross_ttm = ttm(quarters, "gross_profit")
    latest = quarters[0] if quarters else {}
    shares = latest.get("shares_diluted")
    total_debt = latest.get("total_debt")
    cash = latest.get("cash_and_equivalents")
    total_equity = latest.get("total_equity")

    # základ
    m.market_cap = None if (close is None or shares is None) else close * shares
    if total_debt is not None and cash is not None:
        m.net_debt = total_debt - cash
    if m.market_cap is not None and m.net_debt is not None:
        m.enterprise_value = m.market_cap + m.net_debt
    if cfo_ttm is not None and capex_ttm is not None:
        m.fcf_ttm = cfo_ttm - abs(capex_ttm)

    # odhady EPS/revenue
    cy_eps = estimates.get(("current_y", "eps"), {}).get("avg")
    ny_eps = estimates.get(("next_y", "eps"), {}).get("avg")
    cy_rev = estimates.get(("current_y", "revenue"), {}).get("avg")
    eps_ntm_v = eps_ntm(cy_eps, ny_eps, fy_end_month, as_of)

    # násobky
    if close is not None and eps_ttm_v and eps_ttm_v > 0:
        m.pe_ttm = close / eps_ttm_v
    if close is not None and eps_ntm_v and eps_ntm_v > 0:
        m.pe_fwd = close / eps_ntm_v
    if m.enterprise_value is not None and ebitda_ttm and ebitda_ttm > 0:
        m.ev_ebitda = m.enterprise_value / ebitda_ttm
    if m.enterprise_value is not None and revenue_ttm:
        m.ev_sales = safe_div(m.enterprise_value, revenue_ttm)
    if m.market_cap is not None and m.fcf_ttm and m.fcf_ttm > 0:
        m.p_fcf = m.market_cap / m.fcf_ttm

    # růst
    m.revenue_yoy_ttm = yoy_ttm(quarters, "revenue")
    m.eps_yoy_ttm = yoy_ttm(quarters, "eps_diluted")
    # Pojistka proti glitchům rekonstrukce TTM (díry/změna XBRL tagů): nereálné
    # meziroční tempo u zavedených firem = chyba dat → zahoď.
    for _attr in ("revenue_yoy_ttm", "eps_yoy_ttm"):
        _v = getattr(m, _attr)
        if _v is not None and (_v > 300 or _v < -95):
            setattr(m, _attr, None)
            m.notes.append(f"{_attr} zahozeno jako nereálné ({_v:.0f}% — glitch dat)")
    m.eps_growth_ntm = pct(eps_ntm_v, eps_ttm_v)
    m.revenue_growth_ntm = pct(cy_rev, revenue_ttm)
    if m.eps_growth_ntm is not None and m.eps_yoy_ttm is not None:
        m.growth_accel = m.eps_growth_ntm - m.eps_yoy_ttm
    # Bez forward odhadů použij trailing růst, ať growth score není prázdné
    if m.eps_growth_ntm is None and m.eps_yoy_ttm is not None:
        m.eps_growth_ntm = m.eps_yoy_ttm
        m.notes.append("eps_growth_ntm = trailing eps_yoy (bez forward odhadů)")
    if m.revenue_growth_ntm is None and m.revenue_yoy_ttm is not None:
        m.revenue_growth_ntm = m.revenue_yoy_ttm
        m.notes.append("revenue_growth_ntm = trailing revenue_yoy (bez forward odhadů)")

    if m.pe_fwd is not None and m.eps_growth_ntm and m.eps_growth_ntm > 0:
        m.peg_fwd = m.pe_fwd / m.eps_growth_ntm

    # kvalita
    m.gross_margin = _mul100(safe_div(gross_ttm, revenue_ttm))
    m.operating_margin = _mul100(safe_div(op_income_ttm, revenue_ttm))
    m.fcf_margin = _mul100(safe_div(m.fcf_ttm, revenue_ttm))
    if op_income_ttm is not None and total_debt is not None and total_equity is not None and cash is not None:
        nopat = op_income_ttm * (1 - TAX_RATE)
        m.roic = _mul100(safe_div(nopat, total_debt + total_equity - cash))
    m.net_debt_to_ebitda = safe_div(m.net_debt, ebitda_ttm)
    op_margin_prev = safe_div(ttm(quarters[4:8], "operating_income"), ttm(quarters[4:8], "revenue"))
    if m.operating_margin is not None and op_margin_prev is not None:
        m.margin_trend = m.operating_margin - op_margin_prev * 100
    shares_prev = quarters[4].get("shares_diluted") if len(quarters) > 4 else None
    m.share_count_change = pct(shares, shares_prev)

    # momentum odhadů
    tr = trend.get("current_y", {})
    up, down = tr.get("up_last_30d"), tr.get("down_last_30d")
    if up is not None and down is not None:
        denom = max(up + down, 1)
        m.revision_ratio_30d = (up - down) / denom
    cur, d90 = tr.get("current"), tr.get("days_ago_90")
    if cur is not None and d90 not in (None, 0):
        m.estimate_drift_90d = (cur - d90) / abs(d90)
    if surprises:
        s4 = [x for x in surprises[:4] if x is not None]
        if s4:
            m.avg_surprise_4q = sum(s4) / len(s4)

    # trend a riziko (z denních cen ASC)
    closes = [p["close"] for p in prices if p.get("close") is not None]
    if len(closes) >= 200 and close is not None:
        sma200 = sum(closes[-200:]) / 200
        m.px_vs_sma200 = _mul100(safe_div(close, sma200) - 1) if sma200 else None
    if len(closes) >= 252:
        # 12-1 momentum: výnos za ~12M bez posledního ~1M (21 dní)
        if closes[-21] and closes[-252]:
            m.mom_12_1 = _mul100(closes[-21] / closes[-252] - 1)
        window = closes[-252:]
        peak = window[0]
        max_dd = 0.0
        for c in window:
            peak = max(peak, c)
            if peak:
                max_dd = min(max_dd, c / peak - 1)
        m.max_dd_1y = _mul100(max_dd)
    if len(closes) >= 61:
        rets = [closes[i] / closes[i - 1] - 1 for i in range(len(closes) - 60, len(closes)) if closes[i - 1]]
        if len(rets) >= 30:
            m.realized_vol_60d = _mul100(statistics.pstdev(rets) * (252 ** 0.5))

    # historické percentily (point-in-time)
    pe_series = historical_pe_series(quarters, prices)
    m.pctile_pe_ttm = percentile_rank(pe_series, m.pe_ttm)
    # pe_fwd nemá 5y historii forwardových odhadů → percentil vůči vlastní TTM-historii
    # (transparentní proxy: jak dnešní forward násobek stojí vůči trailing historii firmy)
    m.pctile_pe_fwd = percentile_rank(pe_series, m.pe_fwd)
    if m.pctile_pe_fwd is not None:
        m.notes.append("pctile_pe_fwd = percentil vůči vlastní pe_ttm historii (chybí 5y fwd odhadů)")
    # Bez forward odhadů (jen výkazy, např. SEC) použij trailing percentil, ať
    # valuace i osa mapy fungují z reálných dat.
    if m.pctile_pe_fwd is None and m.pctile_pe_ttm is not None:
        m.pctile_pe_fwd = m.pctile_pe_ttm
        m.notes.append("pctile_pe_fwd = trailing pe_ttm percentil (bez forward odhadů)")

    if not eps_ttm_v:
        m.notes.append("TTM EPS chybí (< 4 kvartály nebo NULL)")

    return m


def _mul100(x: float | None) -> float | None:
    return None if x is None else x * 100.0
