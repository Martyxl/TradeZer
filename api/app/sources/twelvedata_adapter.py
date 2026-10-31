"""Twelve Data — 1min svíčky pro měření reakcí na zprávy (forex, zlato, BTC).

Proti Yahoo: 1min místo 5min (přesnější cena „před zprávou“ i okna 5/10/30 min), spot zlato místo
futures GC=F a historie od roku 2020 (Yahoo 5m jen ~60 dní). US indexové futures (ES/NQ/YM) v plánu
nejsou → zůstávají na Yahoo (ETF SPY/QQQ by v 8:30 ET neobchodovaly).

Pozor: Twelve Data vrací forex/kovy i o víkendu (syntetické kotace — EUR/USD skáče desítky pipů,
zlato stojí). Bary mimo obchodní dobu (pá 17:00 → ne 17:00 New York) se zahazují, jinak by víkendová
zpráva nevypadala jako „trh zavřený“ (gap) a reakce by se měřila na šumu.

Env: TWELVEDATA_API_KEY (bez něj adaptér vrací None a kalibrace jede z Yahoo).
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import structlog

log = structlog.get_logger(__name__)

NY = ZoneInfo("America/New_York")
SYMBOL_MAP = {
    "EURUSD": "EUR/USD",
    "GBPUSD": "GBP/USD",
    "USDJPY": "USD/JPY",
    "XAUUSD": "XAU/USD",
    "BTCUSD": "BTC/USD",
}
ALWAYS_OPEN = {"BTCUSD"}
BAR_SECONDS = 60


def api_key() -> str:
    return (os.environ.get("TWELVEDATA_API_KEY") or "").strip()


def supports(symbol: str) -> bool:
    return bool(api_key()) and symbol in SYMBOL_MAP


def fx_open(ts: float) -> bool:
    """Forex/kovy: týden běží od neděle 17:00 do pátku 17:00 New York (letní/zimní čas sám)."""
    ny = datetime.fromtimestamp(ts, tz=NY)
    wd, h = ny.weekday(), ny.hour  # po=0 … ne=6
    if wd == 5:
        return False
    if wd == 4:
        return h < 17
    if wd == 6:
        return h >= 17
    return True


def _fetch(symbol: str, start: datetime, end: datetime) -> list[dict] | None:
    """1min bary [start, end) jako [{t, close, high, low, s}] (t = začátek svíčky, UTC epoch).
    None = chyba sítě/API (zkusit znovu), [] = žádná data."""
    out: list[dict] = []
    cur = start
    while cur < end:  # 5000 barů na volání ≈ 3,4 dne
        chunk_end = min(end, cur + timedelta(minutes=4999))
        try:
            r = httpx.get("https://api.twelvedata.com/time_series", timeout=30.0,
                          headers={"Authorization": f"apikey {api_key()}"},
                          params={"symbol": SYMBOL_MAP[symbol], "interval": "1min", "timezone": "UTC",
                                  "order": "ASC", "outputsize": 5000,
                                  "start_date": cur.strftime("%Y-%m-%d %H:%M:%S"),
                                  "end_date": chunk_end.strftime("%Y-%m-%d %H:%M:%S")})
            d = r.json()
        except Exception as e:  # noqa: BLE001
            log.warning("Twelve Data request failed", symbol=symbol, error=str(e)[:200])
            return None
        if d.get("status") == "error":
            if d.get("code") == 400 and "No data" in (d.get("message") or ""):
                pass  # v rozsahu nic (svátek, víkend)
            else:
                log.warning("Twelve Data error", symbol=symbol, code=d.get("code"), msg=(d.get("message") or "")[:200])
                return None
        for b in d.get("values") or []:
            t = datetime.strptime(b["datetime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
            if symbol not in ALWAYS_OPEN and not fx_open(t):
                continue
            c = float(b["close"])
            out.append({"t": t, "close": c, "high": float(b.get("high") or c), "low": float(b.get("low") or c),
                        "s": BAR_SECONDS})
        cur = chunk_end
    return out


class TwelveDataAdapter:
    """Stejné rozhraní jako YahooFinanceAdapter (fetch_day_bars / fetch_range_bars), jen 1min bary."""

    def fetch_day_bars(self, symbol: str, for_date: date) -> list[dict] | None:
        start = datetime(for_date.year, for_date.month, for_date.day, tzinfo=timezone.utc)
        return _fetch(symbol, start, start + timedelta(days=2))

    def fetch_range_bars(self, symbol: str, start: date, end: date) -> list[dict] | None:
        return _fetch(symbol, datetime(start.year, start.month, start.day, tzinfo=timezone.utc),
                      datetime(end.year, end.month, end.day, tzinfo=timezone.utc))
