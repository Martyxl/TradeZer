"""Yahoo Finance adaptér pro historická tržní data."""
from datetime import datetime, timedelta, timezone, date

import httpx
import structlog

log = structlog.get_logger(__name__)

SYMBOL_MAP = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "XAUUSD": "GC=F",
    "BTCUSD": "BTC-USD",
    "ES": "ES=F",
    "NQ": "NQ=F",
}

# Yahoo Finance chart API (same endpoint yfinance uses internally)
YF_CHART_URL = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _fetch_chart(symbol: str, period1: int, period2: int, interval: str = "5m") -> list[dict]:
    """
    Stáhne OHLCV data přímo z Yahoo Finance chart API.
    Vrátí seznam {"t": epoch_seconds, "close": float}.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    params = {
        "symbol": symbol,
        "period1": period1,
        "period2": period2,
        "interval": interval,
        "includePrePost": "true",
        "events": "div|split",
    }
    try:
        with httpx.Client(timeout=15.0, headers=headers, follow_redirects=True) as client:
            resp = client.get(YF_CHART_URL.format(symbol=symbol), params=params)
            resp.raise_for_status()
            data = resp.json()

        result_data = data.get("chart", {}).get("result")
        if not result_data:
            error = data.get("chart", {}).get("error")
            log.warning("Yahoo Finance chart API error", symbol=symbol, error=error)
            return []

        timestamps = result_data[0].get("timestamp", [])
        closes = result_data[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])

        bars = [
            {"t": t, "close": c}
            for t, c in zip(timestamps, closes)
            if t is not None and c is not None
        ]
        log.debug("Yahoo Finance chart fetched", symbol=symbol, bars=len(bars))
        return bars

    except Exception as e:
        log.warning("Yahoo Finance chart fetch failed", symbol=symbol, error=str(e))
        return []


def _find_close_at(bars: list[dict], target_utc: datetime, tolerance_minutes: int = 30) -> float | None:
    """Z načteného seznamu barů najde Close nejblíže target_utc."""
    if not bars:
        return None
    target_epoch = target_utc.timestamp()
    tolerance_sec = tolerance_minutes * 60
    best = None
    best_diff = float("inf")
    for bar in bars:
        diff = abs(bar["t"] - target_epoch)
        if diff < best_diff and diff <= tolerance_sec:
            best_diff = diff
            best = bar["close"]
    return best


class YahooFinanceAdapter:
    """Stahuje OHLCV data pro kalibraci market reactions."""

    def fetch_day_bars(self, ticker_symbol: str, for_date: date) -> list[dict]:
        """
        Stáhne celý den 5min barů pro daný ticker a datum.
        Vhodné pro hromadné vyhledávání — stáhni jednou, použij mnohokrát.
        """
        yahoo_sym = SYMBOL_MAP.get(ticker_symbol, ticker_symbol)
        day_start = datetime(for_date.year, for_date.month, for_date.day, tzinfo=timezone.utc)
        # +2 dny pro 1d reakci a pro futures s non-standard seancemi
        day_end = day_start + timedelta(days=2)
        period1 = int(day_start.timestamp())
        period2 = int(day_end.timestamp())
        return _fetch_chart(yahoo_sym, period1, period2, interval="5m")

    def get_prices_for_reaction(
        self, ticker_symbol: str, news_time: datetime
    ) -> dict[str, float | None]:
        """
        Stáhne data pro daný den a vyhledá ceny v čase zprávy, +15min, +1h, +1d.
        """
        news_utc = _to_utc(news_time)
        bars = self.fetch_day_bars(ticker_symbol, news_utc.date())

        return {
            "at_news": _find_close_at(bars, news_utc),
            "15m": _find_close_at(bars, news_utc + timedelta(minutes=15)),
            "1h": _find_close_at(bars, news_utc + timedelta(hours=1)),
            "1d": _find_close_at(bars, news_utc + timedelta(days=1), tolerance_minutes=60),
        }
