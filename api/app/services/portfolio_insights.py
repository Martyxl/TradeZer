"""Investorský deník: očekávané dividendy a rozložení portfolia (vč. obsahu ETF).

Vstup = pozice uživatele (počet kusů, hodnota v základní měně) + profil titulů z Twelve Data
(InvestmentSymbolMeta). Čisté funkce bez DB → testovatelné.

Dividendy: vyhlášené výplaty + odhad dalších podle dosavadní frekvence a poslední částky
(firma může dividendu změnit nebo zrušit — proto „odhad“). Rozložení: akcie podle svého sektoru
a země, ETF rozpuštěné podle svého obsahu (sektory, země, největší pozice).
"""
from __future__ import annotations

from datetime import date, timedelta
from statistics import median

SECTOR_CS = {
    "technology": "Technologie", "consumer non-cyclicals": "Základní spotřeba", "consumer defensive": "Základní spotřeba",
    "consumer cyclicals": "Cyklická spotřeba", "consumer cyclical": "Cyklická spotřeba", "consumer services": "Cyklická spotřeba",
    "consumer durables": "Cyklická spotřeba", "retail trade": "Cyklická spotřeba",
    "finance": "Finance", "financial services": "Finance", "financial": "Finance",
    "healthcare": "Zdravotnictví", "health care": "Zdravotnictví", "health technology": "Zdravotnictví",
    "health services": "Zdravotnictví",
    "industrials": "Průmysl", "producer manufacturing": "Průmysl", "transportation": "Průmysl",
    "energy": "Energie", "energy minerals": "Energie", "utilities": "Utility",
    "real estate": "Nemovitosti", "communication services": "Komunikace", "communications": "Komunikace",
    "telecommunications": "Komunikace", "basic materials": "Materiály", "non-energy minerals": "Materiály",
    "process industries": "Materiály", "business services": "Služby firmám", "commercial services": "Služby firmám",
    "electronic technology": "Technologie", "technology services": "Technologie", "other": "Ostatní",
}
COUNTRY_CS = {
    "united states": "USA", "china": "Čína", "hong kong": "Hongkong", "germany": "Německo", "netherlands": "Nizozemsko",
    "united kingdom": "Velká Británie", "france": "Francie", "switzerland": "Švýcarsko", "japan": "Japonsko",
    "taiwan": "Tchaj-wan", "south korea": "Jižní Korea", "canada": "Kanada", "ireland": "Irsko", "india": "Indie",
    "czech republic": "Česko", "czechia": "Česko", "singapore": "Singapur", "israel": "Izrael", "other": "Ostatní",
}
UNKNOWN = "Nezařazeno"


def _cs(table: dict, name: str | None) -> str:
    if not name:
        return UNKNOWN
    return table.get(name.strip().lower(), name.strip())


def _d(v) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def project_dividends(meta: dict, today: date, horizon_days: int = 365) -> list[dict]:
    """[{ex_date, amount, status: announced|estimate}] na `horizon_days` dopředu (na akcii)."""
    hist = {}
    for x in (meta.get("dividends") or []) + (meta.get("announced") or []):
        d, a = _d(x.get("ex_date")), x.get("amount")
        if d and a:
            hist[d] = float(a)
    if not hist:
        return []
    dates = sorted(hist)
    end = today + timedelta(days=horizon_days)
    out = [{"ex_date": d, "amount": hist[d], "status": "announced"} for d in dates if today <= d <= end]
    past = [d for d in dates if d < today]
    recent = dates[-6:]
    gaps = [(b - a).days for a, b in zip(recent, recent[1:]) if (b - a).days > 20]
    if len(dates) >= 2 and gaps:
        gap = median(gaps)
    elif len(dates) == 1 and (today - dates[0]).days < 400:
        gap = 365
    else:
        return out
    # Firma, která dlouho nevyplatila (víc než 1,5× obvyklé mezery), dividendu nejspíš přerušila.
    if past and not out and (today - past[-1]).days > gap * 1.5 + 30:
        return out
    last, amount = dates[-1], hist[dates[-1]]
    nxt = last + timedelta(days=round(gap))
    while nxt <= end:
        if nxt >= today:
            out.append({"ex_date": nxt, "amount": amount, "status": "estimate"})
        nxt += timedelta(days=round(gap))
    return out


def _add(acc: dict, key: str, v: float) -> None:
    acc[key] = acc.get(key, 0.0) + v


def _shares(acc: dict, total: float, top: int | None = None) -> list[dict]:
    rows = sorted(({"name": k, "value": round(v, 2), "pct": round(v / total * 100, 1)} for k, v in acc.items() if v > 0),
                  key=lambda r: -r["value"])
    return rows[:top] if top else rows


def build_insights(positions: list[dict], metas: dict[str, dict], fx_to_base, today: date) -> dict:
    """positions = [{symbol, name, quantity, currency, value_base}]; fx_to_base(amount, ccy) → base | None."""
    payments, annual, unpriced = [], 0.0, []
    sectors: dict[str, float] = {}
    countries: dict[str, float] = {}
    exposure: dict[str, float] = {}
    total = 0.0
    for p in positions:
        meta = metas.get(p["symbol"].upper()) or {}
        for x in project_dividends(meta, today):
            gross = x["amount"] * p["quantity"]
            base = fx_to_base(gross, p["currency"])
            payments.append({"symbol": p["symbol"], "name": p.get("name"), "ex_date": x["ex_date"].isoformat(),
                             "per_share": x["amount"], "quantity": p["quantity"], "currency": p["currency"],
                             "gross": round(gross, 2), "gross_base": round(base, 2) if base is not None else None,
                             "status": x["status"]})
            if base is not None:
                annual += base
            elif p["symbol"] not in unpriced:
                unpriced.append(p["symbol"])
        v = p.get("value_base")
        if not v:
            continue
        total += v
        etf = meta.get("etf")
        if etf and (etf.get("sectors") or etf.get("countries")):
            for key, items, acc, table in (("sector", etf.get("sectors"), sectors, SECTOR_CS),
                                           ("country", etf.get("countries"), countries, COUNTRY_CS)):
                wsum = 0.0
                for it in items or []:
                    w = float(it.get("weight" if key == "sector" else "allocation") or 0)
                    if w > 0:
                        _add(acc, _cs(table, it.get(key)), v * w)
                        wsum += w
                if wsum < 0.999:
                    _add(acc, UNKNOWN, v * max(0.0, 1 - wsum))
            for h in etf.get("top") or []:
                if h.get("weight"):
                    _add(exposure, h.get("name") or h.get("symbol") or "?", v * float(h["weight"]))
        else:
            _add(sectors, _cs(SECTOR_CS, meta.get("sector")), v)
            _add(countries, _cs(COUNTRY_CS, meta.get("country")), v)
            _add(exposure, p.get("name") or p["symbol"], v)
    payments.sort(key=lambda x: x["ex_date"])
    return {
        "dividends": {"payments": payments, "annual_base": round(annual, 2),
                      "yield_pct": round(annual / total * 100, 2) if total else None,
                      "missing_fx": unpriced},
        "allocation": {"total_base": round(total, 2), "sectors": _shares(sectors, total) if total else [],
                       "countries": _shares(countries, total) if total else [],
                       "top_exposure": _shares(exposure, total, top=10) if total else []},
        "has_meta": bool(metas),
    }
