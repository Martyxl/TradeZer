"""FRED (St. Louis Fed) — ZDARMA actual hodnoty makro eventů pro outlook_eval.

Doplňuje ForexFactory, jehož 'actual' nedorážejí spolehlivě. Mapuje titulek eventu
→ FRED sérii + transformaci → naformátuje výsledek do STEJNÉHO tvaru jako FF forecast
('0.3%', '218K', '4.1%', '180K'), aby šel porovnat (_realized_bucket).

Vyžaduje FRED_API_KEY (zdarma: https://fred.stlouisfed.org/docs/api/api_key.html).
Bezpečná degradace: neznámá série / stará data / chybějící klíč → None (event zůstane
nevyhodnocený, žádná škoda). ISM/PMI/sentiment FRED nemá (proprietární) → nemapováno.

POZN.: ID sérií jsou z veřejného FRED katalogu; při zapojení ověřit živě s klíčem
(špatné ID vrátí chybu → None, takže degraduje bezpečně).
"""
from __future__ import annotations

import datetime as _dt

import httpx
import structlog

from app.config import settings

log = structlog.get_logger(__name__)

_BASE = "https://api.stlouisfed.org/fred/series/observations"

# Uspořádané matchery: VŠECHNY substringy v `need` musí být v titulku (lowercase).
# transform: level | level_k | mom_pct | yoy_pct | chg_thous
#   level     = poslední hodnota (např. UNRATE 4.1 -> "4.1%")
#   level_k   = poslední hodnota / 1000, formát "K" (ICSA 218000 -> "218K")
#   mom_pct   = (poslední − předchozí)/předchozí ×100 (index level -> MoM %)
#   yoy_pct   = (poslední − před 12 obs)/… ×100 (YoY %)
#   chg_thous = poslední − předchozí (série už v tisících) -> "K" (PAYEMS -> "180K")
_MATCHERS: list[dict] = [
    {"need": ["core cpi", "y/y"], "series": "CPILFENS", "t": "yoy_pct", "u": "%", "stale": 45},
    {"need": ["core cpi", "m/m"], "series": "CPILFESL", "t": "mom_pct", "u": "%", "stale": 45},
    {"need": ["cpi", "y/y"], "series": "CPIAUCNS", "t": "yoy_pct", "u": "%", "stale": 45},
    {"need": ["cpi", "m/m"], "series": "CPIAUCSL", "t": "mom_pct", "u": "%", "stale": 45},
    {"need": ["core pce", "m/m"], "series": "PCEPILFE", "t": "mom_pct", "u": "%", "stale": 45},
    {"need": ["pce price", "m/m"], "series": "PCEPI", "t": "mom_pct", "u": "%", "stale": 45},
    {"need": ["ppi", "m/m"], "series": "PPIFIS", "t": "mom_pct", "u": "%", "stale": 45},
    {"need": ["average hourly earnings", "m/m"], "series": "CES0500000003", "t": "mom_pct", "u": "%", "stale": 45},
    {"need": ["core retail sales", "m/m"], "series": "RSFSXMV", "t": "mom_pct", "u": "%", "stale": 55},
    {"need": ["retail sales", "m/m"], "series": "RSAFS", "t": "mom_pct", "u": "%", "stale": 55},
    {"need": ["unemployment rate"], "series": "UNRATE", "t": "level", "u": "%", "stale": 45},
    {"need": ["unemployment claims"], "series": "ICSA", "t": "level_k", "u": "", "stale": 14},
    {"need": ["jobless claims"], "series": "ICSA", "t": "level_k", "u": "", "stale": 14},
    {"need": ["non-farm"], "series": "PAYEMS", "t": "chg_thous", "u": "", "stale": 45},
    {"need": ["nonfarm"], "series": "PAYEMS", "t": "chg_thous", "u": "", "stale": 45},
    {"need": ["gdp", "q/q"], "series": "A191RL1Q225SBEA", "t": "level", "u": "%", "stale": 120},
    {"need": ["gdp"], "series": "A191RL1Q225SBEA", "t": "level", "u": "%", "stale": 120},
]


def _match(title_low: str) -> dict | None:
    for m in _MATCHERS:
        if all(s in title_low for s in m["need"]):
            return m
    return None


async def _fetch_obs(series_id: str, limit: int = 16) -> list[tuple[str, float]] | None:
    """Poslední pozorování (newest first) jako [(date, value)]; None při chybě."""
    if not settings.fred_api_key:
        return None
    params = {
        "series_id": series_id, "api_key": settings.fred_api_key,
        "file_type": "json", "sort_order": "desc", "limit": str(limit),
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as cl:
            r = await cl.get(_BASE, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:  # noqa: BLE001
        log.warning("FRED fetch failed", series=series_id, error=str(e))
        return None
    out = []
    for o in data.get("observations", []):
        v = o.get("value")
        if v in (".", "", None):
            continue
        try:
            out.append((o["date"], float(v)))
        except (ValueError, KeyError):
            continue
    return out or None


def _format(m: dict, obs: list[tuple[str, float]]) -> str | None:
    tr, u = m["t"], m["u"]
    try:
        v0 = obs[0][1]
        if tr == "level":
            return f"{v0:.1f}%" if u == "%" else f"{v0:g}"
        if tr == "level_k":
            return f"{round(v0 / 1000)}K"
        idx = 12 if tr == "yoy_pct" else 1
        if len(obs) <= idx:
            return None
        vp = obs[idx][1]
        if tr in ("mom_pct", "yoy_pct"):
            if vp == 0:
                return None
            return f"{(v0 - vp) / vp * 100:.1f}%"
        if tr == "chg_thous":
            return f"{round(v0 - vp)}K"
    except (ValueError, ZeroDivisionError, IndexError):
        return None
    return None


async def get_event_actual(title: str, event_date: _dt.date) -> str | None:
    """Actual hodnota eventu z FRED ve tvaru jako FF forecast, nebo None.
    Freshness guard: použij jen pokud poslední pozorování FRED je čerstvé (release
    proběhl) — jinak by hrozilo použití staré hodnoty z minulého vydání."""
    t = (title or "").lower()
    if "adp" in t:  # ADP ≠ oficiální BLS payrolls; FRED čistou ADP sérii nemapujeme
        return None
    m = _match(t)
    if m is None:
        return None
    obs = await _fetch_obs(m["series"])
    if not obs:
        return None
    try:
        latest = _dt.date.fromisoformat(obs[0][0])
    except (ValueError, IndexError):
        return None
    if (event_date - latest).days > m["stale"]:
        log.info("FRED not fresh yet", series=m["series"], latest=str(latest), event_date=str(event_date))
        return None
    val = _format(m, obs)
    if val is not None:
        log.info("FRED actual", series=m["series"], title=title[:40], value=val)
    return val
