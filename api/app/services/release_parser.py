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

# Ukazatele, které vydávají jen USA (titulek často zemi neuvádí: „JOLTS job openings…“).
_US_ONLY = ("umich", "jolts", "ism ", "adp", "non-farm", "nonfarm", "caseshiller", "case-shiller",
            "conference board", "nahb", "philly fed", "empire", "chicago pmi", "gdpnow", "challenger")
_INFLATION = ("cpi", "ppi", "pce", "inflation", "deflator", "wage", "earnings")
_LABOR = ("payroll", "non-farm", "nonfarm", "claims", "adp", "unemployment", "jolts", "employment",
          "job openings", "jobs")

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
    def category(self) -> str:
        """inflation | labor | growth — jiná logika reakce trhu (viz prompty)."""
        d = self.desc.lower()
        if any(k in d for k in _INFLATION) and "house price" not in d and "home price" not in d:
            return "inflation"
        if any(k in d for k in _LABOR):
            return "labor"
        return "growth"

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
    if any(k in d + " " for k in _US_ONLY):
        return "USD"
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
    return (f"RELEASED DATA [{r.category} data]: {r.desc} — actual {r.actual:g}{r.unit} vs forecast "
            f"{r.compare:g}{r.unit}{pol} → {verdict} for {r.currency or 'the issuing economy'}.")


def release_anchor(title: str, published: datetime) -> datetime:
    """Čas, od kterého měřit reakci. Vydání dat chodí v :00/:15/:30/:45 a investingLive je publikuje
    0–8 min poté → reakce se musí měřit od PLÁNOVANÉHO času vydání (jinak skok ceny už proběhl).
    Ostatní zprávy: čas publikace."""
    r = parse_release(title)
    if r is None or not r.is_forecast:
        return published
    q = published.replace(minute=(published.minute // 15) * 15, second=0, microsecond=0)
    return q if published - q <= timedelta(minutes=8) else published


# ---------------------------------------------------------------------------------------------
# Párování události z kalendáře (ForexFactory) s vydáním z investingLive → skutečná hodnota.
_PERIOD_TAG = re.compile(r"\b(m/m|y/y|q/q|mom|yoy|qoq)\b", re.IGNORECASE)
_PERIOD_NORM = {"mom": "m/m", "yoy": "y/y", "qoq": "q/q"}
_SYN = [  # (regex, kanonický token) — sjednocení názvů FF vs. investingLive
    (r"non-?farm (employment change|payrolls?)|\bnfp\b", " nonfarm "),
    (r"(unemployment|jobless|initial) claims", " claims "),
    (r"continuing claims", " contclaims "),
    (r"\b(uom|umich|michigan)\b", " umich "),
    (r"\bism\b", " ism "),
    (r"retails? sales", " retailsales "),
    (r"consumer price index", " cpi "),
    (r"producer price index", " ppi "),
    (r"personal consumption expenditures?", " pce "),
    (r"average (hourly )?earnings", " earnings "),
    (r"(manufacturing|mfg)", " manufacturing "),
]
_DROP = {"us", "u.s.", "usa", "the", "for", "of", "in", "and", "vs", "prelim", "preliminary", "final",
         "flash", "advance", "revised", "index", "change", "rate", "report", "data", "week", "weekly",
         "january", "february", "march", "april", "may", "june", "july", "august", "september",
         "october", "november", "december", "q1", "q2", "q3", "q4", "germany", "german", "eurozone",
         "uk", "japan", "canada", "china", "france", "italy", "national", "sa", "nsa"}
# „rate" vyhazujeme jen jako šum; míra nezaměstnanosti se rozliší tokenem „unemployment".


def _period(t: str) -> str | None:
    m = _PERIOD_TAG.search(t or "")
    return _PERIOD_NORM.get(m.group(1).lower(), m.group(1).lower()) if m else None


def _tokens(t: str) -> set[str]:
    s = " " + (t or "").lower() + " "
    for pat, rep in _SYN:
        s = re.sub(pat, rep, s)
    s = _PERIOD_TAG.sub(" ", s)
    return {w for w in re.findall(r"[a-z][a-z0-9/]+", s) if w not in _DROP and len(w) > 1}


def match_release(event_title: str, event_currency: str, candidates: list[tuple[str, Release]]) -> Release | None:
    """Najde vydání, které odpovídá události z kalendáře. candidates = [(titulek, Release)].

    Konzervativní: stejná měna, pokrytí slov názvu události ≥ 60 %, shodné období (m/m vs y/y),
    jen vydání vůči očekávání. Při nejistotě None (radši žádná hodnota než špatná)."""
    want = _tokens(event_title)
    if not want:
        return None
    ep = _period(event_title)
    best, best_score = None, 0.0
    for title, r in candidates:
        if r.currency != event_currency or not r.is_forecast:
            continue
        rp = _period(title)
        if ep and rp and ep != rp:
            continue
        score = len(want & _tokens(r.desc)) / len(want)
        if score > best_score:
            best, best_score = r, score
    return best if best_score >= 0.6 else None


def format_actual(r: Release, like: str | None = None) -> str:
    """Hodnota ve formátu jako forecast z kalendáře (např. '0.4%', '194K')."""
    v = f"{r.actual:g}"
    unit = r.unit
    if like and like.strip().endswith("%") and unit != "%":
        unit = "%"
    return f"{v}{unit}"
