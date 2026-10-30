"""RTH gap (open 9:30 ET vs. close předchozího dne 16:00 ET) + historická pravděpodobnost zavření.

Backtest (scripts/backtest_gap.py, 30. 10. 2026, 6 let QQQ/SPY/DIA): směr gapu NEpředpovídá směr
NY session (~50 %), ale velikost gapu silně předpovídá, jestli se cena během dne vrátí na včerejší
close (do 0,1 % ~94 %, 1–2 % ~25 %). Proto karta ukazuje pravděpodobnost zavření, ne směr.

Data: ETF proxy (QQQ ≈ NQ, SPY ≈ ES, DIA ≈ YM) — denní bary mají přesný RTH open/close.
Cíl zavření se navíc přepočte na cenu futures (close futures v 16:00 ET předchozího dne).
"""
from __future__ import annotations

import math
import time as _time
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import structlog

from app.sources.yahoo_finance_adapter import HEADERS, SYMBOL_MAP

log = structlog.get_logger(__name__)

GAP_ETF = {"NQ": "QQQ", "ES": "SPY", "YM": "DIA"}
BUCKETS = [(0.0, 0.1), (0.1, 0.25), (0.25, 0.5), (0.5, 1.0), (1.0, 2.0), (2.0, None)]   # |gap| v %
_NY = ZoneInfo("America/New_York")
_STATS_TTL = 12 * 3600
_LIVE_TTL = 60
_cache: dict[str, tuple[float, dict]] = {}


def _chart(symbol: str, **params) -> dict | None:
    try:
        r = httpx.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}", params=params,
                      headers=HEADERS, timeout=15)
        if r.status_code != 200:
            log.warning("Gap chart non-200", symbol=symbol, status=r.status_code)
            return None
        res = r.json().get("chart", {}).get("result")
        return res[0] if res else None
    except Exception as e:  # noqa: BLE001
        log.warning("Gap chart failed", symbol=symbol, error=str(e)[:200])
        return None


def _bars(res: dict | None) -> list[dict]:
    """[{t, o, h, l, c}] — jen kompletní bary."""
    if not res:
        return []
    q = res.get("indicators", {}).get("quote", [{}])[0]
    out = []
    for i, t in enumerate(res.get("timestamp") or []):
        vals = [q.get(k, [None] * (i + 1))[i] for k in ("open", "high", "low", "close")]
        if t is not None and None not in vals:
            out.append({"t": t, "o": vals[0], "h": vals[1], "l": vals[2], "c": vals[3]})
    return out


def _daily(symbol: str, years: int = 6) -> list[dict]:
    p2 = int(_time.time())
    res = _chart(symbol, period1=p2 - years * 365 * 86400, period2=p2, interval="1d", includePrePost="false")
    off = (res or {}).get("meta", {}).get("gmtoffset", 0)
    return [{**b, "d": datetime.fromtimestamp(b["t"] + off, timezone.utc).date()} for b in _bars(res)]


def _wilson(k: int, n: int) -> tuple[float, float] | None:
    if not n:
        return None
    z, p = 1.96, k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return round(100 * (mid - half)), round(100 * (mid + half))


def _bucket_of(abs_pct: float) -> int:
    for i, (lo, hi) in enumerate(BUCKETS):
        if abs_pct >= lo and (hi is None or abs_pct < hi):
            return i
    return len(BUCKETS) - 1


def compute_table(rows: list[dict], today: date | None = None) -> dict:
    """Pravděpodobnost zavření gapu a pokračování ve směru gapu podle velikosti (|gap| v %)."""
    days = []
    for p, r in zip(rows, rows[1:]):
        if today and r["d"] >= today:
            break
        gap = r["o"] / p["c"] - 1
        if gap == 0:
            continue
        up = gap > 0
        days.append({"b": _bucket_of(abs(gap) * 100), "up": up,
                     "filled": r["l"] <= p["c"] if up else r["h"] >= p["c"],
                     "cont": (r["c"] > r["o"]) if up else (r["c"] < r["o"])})

    def agg(items: list[dict]) -> dict:
        n = len(items)
        fill = sum(x["filled"] for x in items)
        cont = sum(x["cont"] for x in items)
        return {"n": n, "fill_pct": round(100 * fill / n) if n else None, "fill_ci": _wilson(fill, n),
                "cont_pct": round(100 * cont / n) if n else None, "cont_ci": _wilson(cont, n)}

    table = []
    for i, (lo, hi) in enumerate(BUCKETS):
        items = [d for d in days if d["b"] == i]
        table.append({"lo": lo, "hi": hi, **agg(items),
                      "up": agg([d for d in items if d["up"]]), "down": agg([d for d in items if not d["up"]])})
    return {"n_days": len(days), "since": str(rows[0]["d"]) if rows else None, "rows": table}


def _stats(etf: str, today: date) -> dict | None:
    key = f"stats:{etf}:{today}"   # nový den → čerstvé denní bary (včerejší close už finální)
    hit = _cache.get(key)
    if hit and _time.time() - hit[0] < _STATS_TTL:
        return hit[1]
    rows = _daily(etf)
    if len(rows) < 100:
        return hit[1] if hit else None
    out = {"rows_daily": rows, **compute_table(rows, today)}
    _cache[key] = (_time.time(), out)
    return out


def _et(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, _NY)


def _fut_close_at_16(fut: str, d: date) -> float | None:
    """Close futures v 16:00 ET dne d (poslední 5m bar začínající před 16:00)."""
    res = _chart(fut, range="5d", interval="5m", includePrePost="true")
    close_ts = datetime.combine(d, time(16, 0), _NY).timestamp()
    seg = [b for b in _bars(res) if close_ts - 3600 <= b["t"] < close_ts]
    return round(seg[-1]["c"], 2) if seg else None


def live_gap(symbol: str, now: datetime | None = None) -> dict | None:
    """Dnešní gap pro instrument (přes ETF proxy) + odpovídající řádek historické tabulky."""
    etf = GAP_ETF.get(symbol.upper())
    if not etf:
        return None
    now_et = (now or datetime.now(timezone.utc)).astimezone(_NY)
    ck = f"live:{etf}"
    hit = _cache.get(ck)
    if now is None and hit and _time.time() - hit[0] < _LIVE_TTL:
        return hit[1]

    today = now_et.date()
    stats = _stats(etf, today)
    if not stats:
        return None
    prev = next((r for r in reversed(stats["rows_daily"]) if r["d"] < today), None)
    if not prev:
        return None
    base = {"ticker": symbol.upper(), "etf": etf, "prev_date": str(prev["d"]), "prev_close": round(prev["c"], 2),
            "table": {k: stats[k] for k in ("n_days", "since", "rows")}}

    res = _chart(etf, range="1d", interval="5m", includePrePost="true")
    bars = [b for b in _bars(res) if _et(b["t"]).date() == today]
    open_ts = datetime.combine(today, time(9, 30), _NY).timestamp()
    close_ts = datetime.combine(today, time(16, 0), _NY).timestamp()
    rth = [b for b in bars if open_ts <= b["t"] < close_ts]
    if today.weekday() >= 5 or not bars:
        out = {**base, "status": "closed"}
    else:
        if rth:
            price = rth[0]["o"]
            status = "closed_today" if now_et.timestamp() >= close_ts else "open"
        else:
            price = bars[-1]["c"]
            status = "premarket"
        gap = price / prev["c"] - 1
        up = gap > 0
        row = stats["rows"][_bucket_of(abs(gap) * 100)]
        filled = None
        if rth:
            filled = any(b["l"] <= prev["c"] for b in rth) if up else any(b["h"] >= prev["c"] for b in rth)
        out = {**base, "status": status, "price": round(price, 2), "last": round(bars[-1]["c"], 2),
               "gap_pct": round(gap * 100, 2), "direction": "up" if up else "down",
               "bucket": {"lo": row["lo"], "hi": row["hi"], **row["up" if up else "down"], "all": {
                   k: row[k] for k in ("n", "fill_pct", "fill_ci", "cont_pct", "cont_ci")}},
               "filled_today": filled}
        fut = SYMBOL_MAP.get(symbol.upper())
        if fut:
            out["fut_symbol"] = symbol.upper()
            out["fut_target"] = _fut_close_at_16(fut, prev["d"])
    _cache[ck] = (_time.time(), out)
    return out
