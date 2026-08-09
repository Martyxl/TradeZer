"""SECEdgarProvider — finanční výkazy z SEC EDGAR (zdarma, oficiální, bez limitů).

Výkazy z XBRL companyfacts. Kvartální hodnoty přes fiskální tagy (fy/fp) +
dopočet Q4 = FY − (Q1+Q2+Q3). Ceny delegovány na FMP free (SEC ceny nemá).
Odhady/revize/earnings: [] (dopočítáme si vlastním modelem z cen/zpráv).

SEC vyžaduje popisný User-Agent (settings.sec_user_agent), jinak 403.
Chybějící hodnota → None (nikdy neimputovat).
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

import httpx
import structlog

from app.config import settings
from app.valuation.providers.base import (
    MarketDataProvider, Profile, FinancialStatement, EstimatePoint,
    RevisionTrend, EarningsRow, PriceBar,
)

log = structlog.get_logger(__name__)

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"

# us-gaap koncepty (kandidáti v pořadí preference)
FLOW_CONCEPTS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss"],
    "cfo": ["NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "dep_amort": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization"],
    "shares_diluted": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
}
INSTANT_CONCEPTS = {
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
    "total_equity": ["StockholdersEquity"],
    "long_term_debt": ["LongTermDebt", "LongTermDebtNoncurrent"],
}
_QUARTERS = ["Q1", "Q2", "Q3", "Q4"]


def _facts_for(facts: dict, names: list[str]) -> list[dict]:
    """Sloučí fakty ze VŠECH kandidátních konceptů (firmy mění XBRL tagy v čase)."""
    ug = facts.get("facts", {}).get("us-gaap", {})
    merged: list[dict] = []
    for n in names:
        if n in ug:
            units = ug[n].get("units", {})
            for unit_key in ("USD", "USD/shares", "shares"):
                if unit_key in units:
                    merged.extend(units[unit_key])
                    break
    return merged


def _dur_days(f: dict) -> int | None:
    try:
        s = date.fromisoformat(f["start"]); e = date.fromisoformat(f["end"])
        return (e - s).days
    except (KeyError, ValueError, TypeError):
        return None


def _flow_by_fyq(facts: dict, names: list[str]) -> dict[tuple[int, str], dict]:
    """Kvartální (≈90d) hodnoty flow konceptu podle (fy, fp). Nejnovější 'filed' vyhrává."""
    out: dict[tuple, dict] = {}
    for f in _facts_for(facts, names):
        fy, fp, form = f.get("fy"), f.get("fp"), f.get("form", "")
        if fy is None or fp not in ("Q1", "Q2", "Q3", "Q4"):
            continue
        d = _dur_days(f)
        if d is None or not (80 <= d <= 100):  # jen 3měsíční, ne YTD
            continue
        key = (int(fy), fp)
        if key not in out or f.get("filed", "") > out[key].get("filed", ""):
            out[key] = {"val": f.get("val"), "end": f.get("end"), "filed": f.get("filed")}
    return out


def _annual_by_fy(facts: dict, names: list[str]) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for f in _facts_for(facts, names):
        fy = f.get("fy")
        if fy is None or f.get("fp") != "FY":
            continue
        d = _dur_days(f)
        if d is None or not (350 <= d <= 380):
            continue
        if int(fy) not in out or f.get("filed", "") > out[int(fy)].get("filed", ""):
            out[int(fy)] = {"val": f.get("val"), "end": f.get("end"), "filed": f.get("filed")}
    return out


def _instant_by_fyq(facts: dict, names: list[str]) -> dict[tuple[int, str], dict]:
    """Rozvahové (okamžité) hodnoty podle (fy, fp); FY = stav ke konci roku (~Q4)."""
    out: dict[tuple, dict] = {}
    for f in _facts_for(facts, names):
        fy, fp = f.get("fy"), f.get("fp")
        if fy is None or fp not in ("Q1", "Q2", "Q3", "Q4", "FY"):
            continue
        norm_fp = "Q4" if fp == "FY" else fp
        key = (int(fy), norm_fp)
        if key not in out or f.get("filed", "") > out[key].get("filed", ""):
            out[key] = {"val": f.get("val"), "end": f.get("end"), "filed": f.get("filed")}
    return out


def _q4(flow_q: dict, annual: dict, fy: int) -> dict | None:
    """Q4 = roční − (Q1+Q2+Q3), pokud máme roční i všechny tři kvartály."""
    if fy not in annual:
        return None
    parts = [flow_q.get((fy, q)) for q in ("Q1", "Q2", "Q3")]
    if any(p is None or p.get("val") is None for p in parts):
        return None
    val = annual[fy]["val"] - sum(p["val"] for p in parts)
    return {"val": val, "end": annual[fy]["end"], "filed": annual[fy]["filed"]}


def parse_companyfacts(facts: dict, max_quarters: int = 12) -> list[FinancialStatement]:
    """Sestaví kvartální výkazy z XBRL companyfacts (čistá funkce, testovatelná)."""
    flows = {k: _flow_by_fyq(facts, names) for k, names in FLOW_CONCEPTS.items()}
    annuals = {k: _annual_by_fy(facts, names) for k, names in FLOW_CONCEPTS.items()}
    instants = {k: _instant_by_fyq(facts, names) for k, names in INSTANT_CONCEPTS.items()}

    # doplň Q4 do flows z ročních
    all_fys = {fy for m in annuals.values() for fy in m}
    for k in flows:
        for fy in all_fys:
            if (fy, "Q4") not in flows[k]:
                q4 = _q4(flows[k], annuals[k], fy)
                if q4:
                    flows[k][(fy, "Q4")] = q4

    # množina (fy, q) kde máme aspoň revenue nebo net_income
    periods = set()
    for k in ("revenue", "net_income"):
        periods |= set(flows[k].keys())

    def fval(concept, fy, q):
        d = flows.get(concept, {}).get((fy, q))
        return d["val"] if d else None

    def ival(concept, fy, q):
        d = instants.get(concept, {}).get((fy, q))
        return d["val"] if d else None

    stmts = []
    for (fy, q) in periods:
        rev = fval("revenue", fy, q)
        ni = fval("net_income", fy, q)
        end = (flows["revenue"].get((fy, q)) or flows["net_income"].get((fy, q)) or {}).get("end")
        filed = (flows["revenue"].get((fy, q)) or flows["net_income"].get((fy, q)) or {}).get("filed")
        if not end:
            continue
        op = fval("operating_income", fy, q)
        da = fval("dep_amort", fy, q)
        ebitda = (op + da) if (op is not None and da is not None) else None
        shares = fval("shares_diluted", fy, q)
        eps = (ni / shares) if (ni is not None and shares) else None
        ltd = ival("long_term_debt", fy, q)
        stmts.append(FinancialStatement(
            period_end=end[:10], period_type="Q", report_date=(filed or "")[:10] or None,
            revenue=rev, gross_profit=fval("gross_profit", fy, q), operating_income=op,
            ebitda=ebitda, net_income=ni, eps_diluted=round(eps, 4) if eps is not None else None,
            shares_diluted=shares, cfo=fval("cfo", fy, q),
            capex=(-abs(fval("capex", fy, q)) if fval("capex", fy, q) is not None else None),
            total_debt=ltd, cash_and_equivalents=ival("cash", fy, q),
            total_equity=ival("total_equity", fy, q)))
    stmts.sort(key=lambda s: s.period_end, reverse=True)
    return stmts[:max_quarters]


class SECEdgarProvider(MarketDataProvider):
    name = "sec"
    _cik_cache: dict[str, int] = {}

    def _headers(self) -> dict:
        return {"User-Agent": settings.sec_user_agent, "Accept-Encoding": "gzip, deflate"}

    def _get_json(self, url: str) -> dict:
        with httpx.Client(timeout=30.0, headers=self._headers()) as c:
            r = c.get(url)
            r.raise_for_status()
            return r.json()

    def _cik(self, ticker: str) -> int | None:
        if not SECEdgarProvider._cik_cache:
            try:
                data = self._get_json(TICKERS_URL)
                for row in data.values():
                    SECEdgarProvider._cik_cache[row["ticker"].upper()] = int(row["cik_str"])
            except Exception as e:  # noqa: BLE001
                log.warning("SEC ticker map failed", error=str(e)[:120])
                return None
        return SECEdgarProvider._cik_cache.get(ticker.upper())

    def get_profile(self, ticker: str) -> Profile | None:
        cik = self._cik(ticker)
        if cik is None:
            return None
        try:
            sub = self._get_json(SUBMISSIONS_URL.format(cik=cik))
        except Exception:
            sub = {}
        shares = None
        try:
            facts = self._get_json(FACTS_URL.format(cik=cik))
            dei = facts.get("facts", {}).get("dei", {}).get("EntityCommonStockSharesOutstanding", {})
            arr = dei.get("units", {}).get("shares", [])
            if arr:
                shares = float(sorted(arr, key=lambda f: f.get("end", ""))[-1]["val"])
        except Exception:
            pass
        return Profile(
            ticker=ticker, name=sub.get("name"),
            exchange=(sub.get("exchanges") or [None])[0],
            currency="USD",
            gics_sector=sub.get("sicDescription"),
            gics_industry=sub.get("sicDescription"),
            shares_outstanding=shares)

    def get_financials(self, ticker: str) -> list[FinancialStatement]:
        cik = self._cik(ticker)
        if cik is None:
            return []
        try:
            facts = self._get_json(FACTS_URL.format(cik=cik))
        except Exception as e:  # noqa: BLE001
            log.warning("SEC companyfacts failed", ticker=ticker, error=str(e)[:120])
            return []
        return parse_companyfacts(facts)

    def get_estimates(self, ticker: str) -> list[EstimatePoint]:
        return []  # SEC odhady nemá; dopočítáme vlastním modelem

    def get_revisions(self, ticker: str) -> list[RevisionTrend]:
        return []

    def get_earnings_history(self, ticker: str) -> list[EarningsRow]:
        return []

    def get_prices(self, ticker: str, start: date, end: date) -> list[PriceBar]:
        # SEC ceny nemá → FMP free (funguje), fallback Yahoo chart adaptér
        if settings.fmp_api_key:
            try:
                from app.valuation.providers.fmp_provider import FMPProvider
                bars = FMPProvider().get_prices(ticker, start, end)
                if bars:
                    return bars
            except Exception:
                pass
        try:
            from app.sources.yahoo_finance_adapter import YahooFinanceAdapter
            ya = YahooFinanceAdapter()
            raw = ya.fetch_day_bars(ticker, end)  # nejlepší dostupné; nemusí pokrýt celý rozsah
            out = []
            for b in raw:
                d = datetime.utcfromtimestamp(b["t"]).date().isoformat()
                out.append(PriceBar(date=d, close=b.get("close"), adj_close=b.get("close"),
                                    high=b.get("high"), low=b.get("low")))
            return out
        except Exception:
            return []
