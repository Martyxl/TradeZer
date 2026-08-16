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
    "net_income": ["NetIncomeLoss", "ProfitLoss",
                   "NetIncomeLossAvailableToCommonStockholdersBasic"],
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


def _days_between(a: str, b: str) -> int:
    return (date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days


def _by_end_duration(facts: dict, names: list[str], lo: int, hi: int) -> dict[str, dict]:
    """Fakty s délkou trvání v [lo, hi] dní, klíčované KONCEM období (ne fy/fp — ty
    firmy jako NVDA tagují nekonzistentně). Nejnovější 'filed' vyhrává."""
    out: dict[str, dict] = {}
    for f in _facts_for(facts, names):
        d = _dur_days(f)
        end = f.get("end")
        if d is None or end is None or not (lo <= d <= hi):
            continue
        if end not in out or f.get("filed", "") > out[end].get("filed", ""):
            out[end] = {"val": f.get("val"), "start": f.get("start"),
                        "end": end, "filed": f.get("filed")}
    return out


def _instant_by_end(facts: dict, names: list[str]) -> dict[str, dict]:
    """Rozvahové (okamžité) hodnoty klíčované koncem období. Nejnovější 'filed' vyhrává."""
    out: dict[str, dict] = {}
    for f in _facts_for(facts, names):
        end = f.get("end")
        if end is None:
            continue
        if end not in out or f.get("filed", "") > out[end].get("filed", ""):
            out[end] = {"val": f.get("val"), "filed": f.get("filed")}
    return out


def parse_companyfacts(facts: dict, max_quarters: int = 44) -> list[FinancialStatement]:
    """Sestaví kvartální výkazy z XBRL companyfacts (čistá funkce, testovatelná).

    Klíč = KONEC období + délka trvání (ne fiskální fy/fp label — ten některé firmy,
    např. NVDA, tagují posunutě mezi ročním a kvartálním výkazem a dopočet Q4 pak
    odečítá kvartály ze špatného roku → záporné hodnoty).
    Q4 dopočet aditivních flow = roční − (3 kvartály uvnitř ročního okna, dle dat).
    shares_diluted je vážený PRŮMĚR (neaditivní) → na konci FY se NEODEČÍTÁ, bere se
    roční hodnota přímo.
    """
    flow_q = {k: _by_end_duration(facts, names, 80, 100) for k, names in FLOW_CONCEPTS.items()}
    flow_a = {k: _by_end_duration(facts, names, 350, 380) for k, names in FLOW_CONCEPTS.items()}
    instants = {k: _instant_by_end(facts, names) for k, names in INSTANT_CONCEPTS.items()}

    additive = [k for k in FLOW_CONCEPTS if k != "shares_diluted"]

    # Q4 aditivních flow: dle DAT najdi 3 kvartály uvnitř ročního okna, odečti od ročního.
    for k in additive:
        q, a = flow_q[k], flow_a[k]
        for a_end, arow in a.items():
            if a_end in q or not arow.get("start") or arow.get("val") is None:
                continue
            a_start = arow["start"]
            inside = sorted(qe for qe in q
                            if a_start < qe < a_end and _days_between(qe, a_end) >= 85)
            if len(inside) != 3 or any(q[qe]["val"] is None for qe in inside):
                continue
            q[a_end] = {"val": arow["val"] - sum(q[qe]["val"] for qe in inside),
                        "start": None, "end": a_end, "filed": arow["filed"]}

    # shares_diluted na FY-konci: roční vážený průměr přímo (NEODEČÍTAT — dá záporné akcie)
    sh_q, sh_a = flow_q["shares_diluted"], flow_a["shares_diluted"]
    for a_end, arow in sh_a.items():
        if a_end not in sh_q and arow.get("val") is not None:
            sh_q[a_end] = {"val": arow["val"], "start": None, "end": a_end, "filed": arow["filed"]}

    # množina období = konce, kde máme revenue nebo net_income
    periods = set(flow_q["revenue"]) | set(flow_q["net_income"])

    def fval(concept: str, end: str):
        d = flow_q[concept].get(end)
        return d["val"] if d else None

    def ival(concept: str, end: str):
        d = instants[concept].get(end)
        return d["val"] if d else None

    stmts = []
    for end in periods:
        rev = fval("revenue", end)
        ni = fval("net_income", end)
        filed = (flow_q["revenue"].get(end) or flow_q["net_income"].get(end) or {}).get("filed")
        op = fval("operating_income", end)
        da = fval("dep_amort", end)
        ebitda = (op + da) if (op is not None and da is not None) else None
        shares = fval("shares_diluted", end)
        eps = (ni / shares) if (ni is not None and shares) else None
        capex = fval("capex", end)
        stmts.append(FinancialStatement(
            period_end=end[:10], period_type="Q", report_date=(filed or "")[:10] or None,
            revenue=rev, gross_profit=fval("gross_profit", end), operating_income=op,
            ebitda=ebitda, net_income=ni, eps_diluted=round(eps, 4) if eps is not None else None,
            shares_diluted=shares, cfo=fval("cfo", end),
            capex=(-abs(capex) if capex is not None else None),
            total_debt=ival("long_term_debt", end), cash_and_equivalents=ival("cash", end),
            total_equity=ival("total_equity", end)))
    out = sorted(stmts, key=lambda s: s.period_end, reverse=True)
    return out[:max_quarters]


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
        # SEC odhady nemá → deleguj na FMP (stable analyst-estimates je i na free tieru).
        if settings.fmp_api_key:
            try:
                from app.valuation.providers.fmp_provider import FMPProvider
                return FMPProvider().get_estimates(ticker)
            except Exception:  # noqa: BLE001
                pass
        return []

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
