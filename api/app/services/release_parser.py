"""Parser vydaných makro dat z titulků (investingLive): „US initial jobless claims 194K vs 200K estimate“.

Proč: kalendář ForexFactory (mirror) nemá pole `actual` → systém nikdy neviděl překvapení
(skutečnost vs. očekávání). investingLive publikuje vydání do pár minut s přesnými čísly
(ověřeno proti BLS API: NFP 9/2026 +29K = 159 044 − 159 015).

parse_release(title) → Release | None. Polarity: u ukazatelů typu nezaměstnanost / žádosti o podporu
znamená VYŠŠÍ hodnota SLABŠÍ ekonomiku → `strength` (síla ekonomiky/měny) má opačné znaménko než surprise.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

# číslo s volitelným znaménkem, měnou a jednotkou: +0.8%, -105.6B, 1.221M, $4.20 billion, 194K
_NUM = r"[+\-−]?\$?\d[\d,]*(?:\.\d+)?\s?(?:%|[KkMmBbTt](?![a-z])|bn|billion|million|trillion|pts?)?"
_PERIOD = r"(?:\s?(?:m/m|y/y|q/q|mom|yoy|qoq|annualized|saar|ann\.?))?"
_KIND = (r"(?P<kind>expected|exp\.?|estimate[sd]?|est\.?|consensus|forecast|prior|previous|prev\.?|"
         r"prelim(?:inary)?|flash|initial|revised)")
_RE = re.compile(
    rf"^(?P<desc>.*?\S)\s(?P<actual>{_NUM}){_PERIOD}\s+vs\.?\s+(?P<cmp>{_NUM}){_PERIOD}"
    rf"(?:\s+{_PERIOD}\s*)?\s*(?:{_KIND})?",
    re.IGNORECASE,
)

_FORECAST_KINDS = {"expected", "exp", "exp.", "estimate", "estimates", "estimated", "est", "est.",
                   "consensus", "forecast"}

# Vyšší hodnota = horší ekonomika (pro směr měny/akcií se surprise otáčí).
_INVERSE = ("unemployment", "jobless", "initial claims", "continuing claims", "claimant count",
            "layoffs", "challenger")

_COUNTRIES = {
    "us": "USD", "u.s.": "USD", "united states": "USD", "atlanta fed": "USD", "philly fed": "USD",
    "empire": "USD", "eurozone": "EUR", "euro area": "EUR", "germany": "EUR", "german": "EUR",
    "france": "EUR", "french": "EUR", "italy": "EUR", "spain": "EUR", "uk": "GBP", "u.k.": "GBP",
    "britain": "GBP", "japan": "JPY", "japanese": "JPY", "tokyo": "JPY", "china": "CNY", "chinese": "CNY",
    "canada": "CAD", "bank of canada": "CAD", "australia": "AUD", "new zealand": "NZD",
    "switzerland": "CHF", "swiss": "CHF",
}


@dataclass
class Release:
    desc: str
    actual: float
    compare: float
    kind: str            # "forecast" (vs očekávání) nebo "prior" (vs předchozí / předběžné)
    currency: str | None
    inverse: bool        # True = vyšší hodnota znamená slabší ekonomiku
    unit: str            # "%", "K", "M", "B", "" …

    @property
    def is_forecast(self) -> bool:
        return self.kind == "forecast"

    @property
    def surprise(self) -> float:
        return self.actual - self.compare

    @property
    def surprise_rel(self) -> float:
        """Relativní překvapení vůči |očekávání| (pro procentní údaje vůči 1 p.b. minimálně)."""
        base = max(abs(self.compare), 1.0 if self.unit == "%" else 1e-9)
        return self.surprise / base

    @property
    def strength(self) -> int:
        """+1 = data silnější než čekáno (silnější ekonomika/měna), −1 slabší, 0 v souladu."""
        if abs(self.surprise_rel) < 0.005:
            return 0
        s = 1 if self.surprise > 0 else -1
        return -s if self.inverse else s


def _to_float(raw: str) -> tuple[float, str]:
    s = raw.strip().replace("−", "-").replace("$", "").replace(",", "").lower()
    unit = ""
    for suf, u in (("billion", "B"), ("million", "M"), ("trillion", "T"), ("bn", "B"), ("pts", ""),
                   ("pt", ""), ("%", "%"), ("k", "K"), ("m", "M"), ("b", "B"), ("t", "T")):
        if s.endswith(suf):
            s, unit = s[: -len(suf)].strip(), u
            break
    return float(s), unit


def _currency(desc: str) -> str | None:
    d = desc.lower()
    for key, ccy in sorted(_COUNTRIES.items(), key=lambda x: -len(x[0])):
        if re.search(rf"(^|\W){re.escape(key)}(\W|$)", d):
            return ccy
    return None


def parse_release(title: str) -> Release | None:
    m = _RE.search(title or "")
    if not m:
        return None
    try:
        actual, ua = _to_float(m.group("actual"))
        compare, uc = _to_float(m.group("cmp"))
    except ValueError:
        return None
    kind_raw = (m.group("kind") or "").lower()
    # Bez slova za číslem („1.221M vs 1.305M“) investingLive uvádí očekávání → bereme jako forecast.
    kind = "forecast" if (not kind_raw or kind_raw in _FORECAST_KINDS) else "prior"
    desc = m.group("desc").strip(" :-")
    if len(desc) < 4:
        return None
    return Release(desc=desc, actual=actual, compare=compare, kind=kind, currency=_currency(desc),
                   inverse=any(k in desc.lower() for k in _INVERSE), unit=ua or uc)


def release_context(title: str) -> str | None:
    """Strukturovaný kontext pro LLM — skutečnost vs. očekávání + polarita ukazatele."""
    r = parse_release(title)
    if r is None or not r.is_forecast:
        return None
    if r.strength == 0:
        verdict = "IN LINE with expectations (no meaningful surprise)"
    else:
        verdict = ("STRONGER economy than expected" if r.strength > 0 else "WEAKER economy than expected")
    pol = " (inverse indicator: HIGHER value = WEAKER economy)" if r.inverse else ""
    return (f"RELEASED DATA: {r.desc} — actual {r.actual:g}{r.unit} vs forecast {r.compare:g}{r.unit}"
            f"{pol} → {verdict} for {r.currency or 'the issuing economy'}.")


def release_anchor(title: str, published: datetime) -> datetime:
    """Čas, od kterého měřit reakci. Vydání dat chodí v :00/:15/:30/:45 a investingLive je publikuje
    0–8 min poté → reakce se musí měřit od PLÁNOVANÉHO času vydání (jinak skok ceny už proběhl).
    Ostatní zprávy: čas publikace."""
    r = parse_release(title)
    if r is None or not r.is_forecast:
        return published
    q = published.replace(minute=(published.minute // 15) * 15, second=0, microsecond=0)
    return q if published - q <= timedelta(minutes=8) else published
