"""YFinanceProvider — primární zdroj (neoficiální Yahoo scraper).

⚠️ LICENČNÍ POZNÁMKA: yfinance je neoficiální scraper Yahoo Finance; Yahoo svá
data označuje jako informativní, ne pro obchodní/investiční účely. OK pro vývoj
a osobní použití. Pro komerční tradezer.app s platícími uživateli je nutný
licencovaný feed (FMP placený, EODHD, Finnhub, Polygon) — díky tomuto rozhraní
je výměna záležitostí jedné třídy.

Mapování yfinance atributů je best-effort a defenzivní: chybí-li řádek/hodnota,
vrací None (nikdy neimputuje). Reálná data mají proměnlivé popisky řádků, takže
zkoušíme víc kandidátů. Ověř/dolaď při prvním `make ingest`.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import structlog

from app.valuation.providers.base import (
    MarketDataProvider, Profile, FinancialStatement, EstimatePoint,
    RevisionTrend, EarningsRow, PriceBar,
)

log = structlog.get_logger(__name__)


def _f(v: Any) -> float | None:
    try:
        if v is None:
            return None
        import math
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _row(df, *labels: str):
    """Vrátí řádek DataFrame podle prvního existujícího popisku (case-insensitive)."""
    if df is None or getattr(df, "empty", True):
        return None
    idx_lower = {str(i).lower(): i for i in df.index}
    for lab in labels:
        real = idx_lower.get(lab.lower())
        if real is not None:
            return df.loc[real]
    return None


def _cell(row, col) -> float | None:
    if row is None:
        return None
    try:
        return _f(row.get(col))
    except Exception:
        return None


class YFinanceProvider(MarketDataProvider):
    name = "yfinance"

    def _ticker(self, ticker: str):
        import yfinance as yf
        return yf.Ticker(ticker)

    def get_profile(self, ticker: str) -> Profile | None:
        info = self._ticker(ticker).info or {}
        if not info:
            return None
        return Profile(
            ticker=ticker,
            name=info.get("longName") or info.get("shortName"),
            exchange=info.get("exchange"),
            currency=info.get("currency"),
            gics_sector=info.get("sector"),
            gics_industry=info.get("industry"),
            shares_outstanding=_f(info.get("sharesOutstanding")),
        )

    def _statements(self, inc, bal, cf, period_type: str) -> list[FinancialStatement]:
        if inc is None or getattr(inc, "empty", True):
            return []
        rev = _row(inc, "Total Revenue", "TotalRevenue")
        gp = _row(inc, "Gross Profit")
        oi = _row(inc, "Operating Income")
        ebitda = _row(inc, "EBITDA", "Normalized EBITDA")
        ni = _row(inc, "Net Income", "Net Income Common Stockholders")
        eps = _row(inc, "Diluted EPS")
        sh = _row(inc, "Diluted Average Shares", "Diluted Average Shares Outstanding")
        debt = _row(bal, "Total Debt")
        cash = _row(bal, "Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments")
        eq = _row(bal, "Stockholders Equity", "Total Equity Gross Minority Interest")
        cfo = _row(cf, "Operating Cash Flow", "Total Cash From Operating Activities")
        capex = _row(cf, "Capital Expenditure", "Capital Expenditures")

        out = []
        for col in inc.columns:
            pe = col.date().isoformat() if hasattr(col, "date") else str(col)[:10]
            out.append(FinancialStatement(
                period_end=pe, period_type=period_type,
                revenue=_cell(rev, col), gross_profit=_cell(gp, col),
                operating_income=_cell(oi, col), ebitda=_cell(ebitda, col),
                net_income=_cell(ni, col), eps_diluted=_cell(eps, col),
                shares_diluted=_cell(sh, col), cfo=_cell(cfo, col),
                capex=_cell(capex, col), total_debt=_cell(debt, col),
                cash_and_equivalents=_cell(cash, col), total_equity=_cell(eq, col),
            ))
        return out

    def get_financials(self, ticker: str) -> list[FinancialStatement]:
        t = self._ticker(ticker)
        q = self._statements(t.quarterly_income_stmt, t.quarterly_balance_sheet, t.quarterly_cashflow, "Q")
        a = self._statements(t.income_stmt, t.balance_sheet, t.cashflow, "FY")
        return q + a

    _HORIZON = {"0q": "current_q", "+1q": "next_q", "0y": "current_y", "+1y": "next_y"}

    def _estimates_for(self, df, metric: str, today: str) -> list[EstimatePoint]:
        if df is None or getattr(df, "empty", True):
            return []
        out = []
        for idx in df.index:
            horizon = self._HORIZON.get(str(idx))
            if not horizon:
                continue
            r = df.loc[idx]
            out.append(EstimatePoint(
                as_of_date=today, horizon=horizon, metric=metric,
                avg=_cell(r, "avg"), low=_cell(r, "low"), high=_cell(r, "high"),
                n_analysts=int(_cell(r, "numberOfAnalysts") or 0) or None,
                year_ago_value=_cell(r, "yearAgoEps") or _cell(r, "yearAgoRevenue"),
            ))
        return out

    def get_estimates(self, ticker: str) -> list[EstimatePoint]:
        t = self._ticker(ticker)
        today = date.today().isoformat()
        return (self._estimates_for(t.earnings_estimate, "eps", today)
                + self._estimates_for(t.revenue_estimate, "revenue", today))

    def get_revisions(self, ticker: str) -> list[RevisionTrend]:
        t = self._ticker(ticker)
        today = date.today().isoformat()
        trend, rev = t.eps_trend, t.eps_revisions
        if trend is None or getattr(trend, "empty", True):
            return []
        out = []
        for idx in trend.index:
            horizon = self._HORIZON.get(str(idx))
            if not horizon:
                continue
            tr = trend.loc[idx]
            rv = rev.loc[idx] if (rev is not None and idx in getattr(rev, "index", [])) else None
            out.append(RevisionTrend(
                as_of_date=today, horizon=horizon,
                current=_cell(tr, "current"), days_ago_7=_cell(tr, "7daysAgo"),
                days_ago_30=_cell(tr, "30daysAgo"), days_ago_60=_cell(tr, "60daysAgo"),
                days_ago_90=_cell(tr, "90daysAgo"),
                up_last_30d=int(_cell(rv, "upLast30days") or 0) if rv is not None else None,
                down_last_30d=int(_cell(rv, "downLast30days") or 0) if rv is not None else None,
            ))
        return out

    def get_earnings_history(self, ticker: str) -> list[EarningsRow]:
        df = self._ticker(ticker).earnings_history
        if df is None or getattr(df, "empty", True):
            return []
        out = []
        for idx in df.index:
            r = df.loc[idx]
            pe = idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10]
            out.append(EarningsRow(
                period_end=pe,
                eps_actual=_cell(r, "epsActual"), eps_estimate=_cell(r, "epsEstimate"),
                surprise_pct=_cell(r, "surprisePercent"),
            ))
        return out

    def get_prices(self, ticker: str, start: date, end: date) -> list[PriceBar]:
        df = self._ticker(ticker).history(start=start.isoformat(), end=end.isoformat(), auto_adjust=False)
        if df is None or getattr(df, "empty", True):
            return []
        out = []
        for idx, r in df.iterrows():
            d = idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10]
            out.append(PriceBar(
                date=d, open=_f(r.get("Open")), high=_f(r.get("High")),
                low=_f(r.get("Low")), close=_f(r.get("Close")),
                adj_close=_f(r.get("Adj Close")) or _f(r.get("Close")),
                volume=_f(r.get("Volume")),
            ))
        return out
