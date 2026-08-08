"""FMPProvider — Financial Modeling Prep (stable endpointy).

Funguje z libovolné IP přes API klíč (na rozdíl od yfinance, který Yahoo blokuje
z datacenter/CI IP). Free tier: ~250 req/den, jen `stable` endpointy; odhady
analytiků a earnings surprises bývají na free omezené → chybí-li, vrací [].
Chybějící hodnota → None (nikdy neimputovat). Klíč z .env (FMP_API_KEY).
"""
from __future__ import annotations

from datetime import date
from typing import Any

import httpx
import structlog

from app.config import settings
from app.valuation.providers.base import (
    MarketDataProvider, Profile, FinancialStatement, EstimatePoint,
    RevisionTrend, EarningsRow, PriceBar,
)

log = structlog.get_logger(__name__)
BASE = "https://financialmodelingprep.com/stable"


def _f(v: Any) -> float | None:
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


class FMPProvider(MarketDataProvider):
    name = "fmp"

    def _get(self, path: str, **params) -> list | dict:
        if not settings.fmp_api_key:
            raise RuntimeError("FMP_API_KEY není nastaven")
        params["apikey"] = settings.fmp_api_key
        with httpx.Client(timeout=25.0) as client:
            r = client.get(f"{BASE}/{path}", params=params)
            r.raise_for_status()
            return r.json()

    def _safe(self, path: str, **params) -> list:
        """Wrapper: prázdno/chyba (typicky premium endpoint na free) → []."""
        try:
            data = self._get(path, **params)
            return data if isinstance(data, list) else [data]
        except Exception as e:  # noqa: BLE001
            log.info("FMP endpoint unavailable", path=path, error=str(e)[:120])
            return []

    def get_profile(self, ticker: str) -> Profile | None:
        rows = self._safe("profile", symbol=ticker)
        if not rows:
            return None
        p = rows[0]
        return Profile(
            ticker=ticker,
            name=p.get("companyName"),
            exchange=p.get("exchange") or p.get("exchangeShortName"),
            currency=p.get("currency"),
            gics_sector=p.get("sector"),
            gics_industry=p.get("industry"),
            shares_outstanding=_f(p.get("sharesOutstanding")),
        )

    def _statements(self, period: str, ptype: str) -> list[FinancialStatement]:
        inc = {r["date"]: r for r in self._safe("income-statement", symbol=self._t, period=period, limit=8) if r.get("date")}
        bal = {r["date"]: r for r in self._safe("balance-sheet-statement", symbol=self._t, period=period, limit=8) if r.get("date")}
        cf = {r["date"]: r for r in self._safe("cash-flow-statement", symbol=self._t, period=period, limit=8) if r.get("date")}
        out = []
        for d, i in inc.items():
            b = bal.get(d, {})
            c = cf.get(d, {})
            out.append(FinancialStatement(
                period_end=d[:10], period_type=ptype,
                report_date=(i.get("filingDate") or i.get("acceptedDate") or "")[:10] or None,
                revenue=_f(i.get("revenue")), gross_profit=_f(i.get("grossProfit")),
                operating_income=_f(i.get("operatingIncome")), ebitda=_f(i.get("ebitda")),
                net_income=_f(i.get("netIncome")),
                eps_diluted=_f(i.get("epsDiluted") or i.get("epsdiluted") or i.get("eps")),
                shares_diluted=_f(i.get("weightedAverageShsOutDil")),
                cfo=_f(c.get("operatingCashFlow") or c.get("netCashProvidedByOperatingActivities")),
                capex=_f(c.get("capitalExpenditure")),
                total_debt=_f(b.get("totalDebt")),
                cash_and_equivalents=_f(b.get("cashAndCashEquivalents")),
                total_equity=_f(b.get("totalStockholdersEquity") or b.get("totalEquity")),
            ))
        return out

    def get_financials(self, ticker: str) -> list[FinancialStatement]:
        self._t = ticker
        # Jen kvartální výkazy — na FMP free šetří 3 requesty/ticker (roční jsou
        # dopočitatelné z 4 kvartálů, fy_end_month default). Roční přidej na placeném tarifu.
        return self._statements("quarter", "Q")

    def get_estimates(self, ticker: str) -> list[EstimatePoint]:
        rows = self._safe("analyst-estimates", symbol=ticker, period="annual", limit=4)
        if not rows:
            return []
        today = date.today()
        out = []
        for r in rows:
            d = (r.get("date") or "")[:10]
            if not d:
                continue
            try:
                yr = int(d[:4])
            except ValueError:
                continue
            horizon = "current_y" if yr == today.year else ("next_y" if yr == today.year + 1 else None)
            if not horizon:
                continue
            out.append(EstimatePoint(
                as_of_date=today.isoformat(), horizon=horizon, metric="eps",
                avg=_f(r.get("estimatedEpsAvg")), low=_f(r.get("estimatedEpsLow")),
                high=_f(r.get("estimatedEpsHigh")),
                n_analysts=int(_f(r.get("numberAnalystEstimatedEps")) or 0) or None))
            out.append(EstimatePoint(
                as_of_date=today.isoformat(), horizon=horizon, metric="revenue",
                avg=_f(r.get("estimatedRevenueAvg")), low=_f(r.get("estimatedRevenueLow")),
                high=_f(r.get("estimatedRevenueHigh")),
                n_analysts=int(_f(r.get("numberAnalystsEstimatedRevenue")) or 0) or None))
        return out

    def get_revisions(self, ticker: str) -> list[RevisionTrend]:
        return []  # na FMP free nedostupné

    def get_earnings_history(self, ticker: str) -> list[EarningsRow]:
        rows = self._safe("earnings", symbol=ticker, limit=8) or self._safe("earnings-surprises", symbol=ticker, limit=8)
        out = []
        for r in rows:
            d = (r.get("date") or "")[:10]
            if not d:
                continue
            act = _f(r.get("epsActual") or r.get("actualEarningResult"))
            est = _f(r.get("epsEstimated") or r.get("estimatedEarning"))
            surprise = None
            if act is not None and est not in (None, 0):
                surprise = round((act - est) / abs(est) * 100, 2)
            out.append(EarningsRow(period_end=d, report_date=d, eps_actual=act,
                                   eps_estimate=est, surprise_pct=surprise))
        return out

    def get_prices(self, ticker: str, start: date, end: date) -> list[PriceBar]:
        rows = self._safe("historical-price-eod/full", symbol=ticker,
                          **{"from": start.isoformat(), "to": end.isoformat()})
        out = []
        for r in rows:
            d = (r.get("date") or "")[:10]
            if not d:
                continue
            out.append(PriceBar(
                date=d, open=_f(r.get("open")), high=_f(r.get("high")),
                low=_f(r.get("low")), close=_f(r.get("close")),
                adj_close=_f(r.get("adjClose") or r.get("adjustedClose") or r.get("close")),
                volume=_f(r.get("volume"))))
        out.sort(key=lambda b: b.date)
        return out
