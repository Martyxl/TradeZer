"""Yahoo Finance adaptér pro historická tržní data.

Yahoo Finance vyžaduje od 2023 crumb token + cookie pro API přístup.
Implementujeme minimální auth flow: cookie fetch → crumb fetch → data fetch.
"""
from datetime import datetime, timedelta, timezone, date
from typing import Optional
import json

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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://finance.yahoo.com/",
    "Origin": "https://finance.yahoo.com",
}


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _get_crumb_and_cookies(client: httpx.Client) -> tuple[str, dict]:
    """Získá crumb token + cookies potřebné pro Yahoo Finance API."""
    # Krok 1: navštiv Yahoo Finance pro cookies
    try:
        r = client.get("https://fc.yahoo.com/v1/test/solicit?mode=user-consent",
                       follow_redirects=True, timeout=10)
    except Exception:
        pass

    # Krok 2: stáhni crumb
    r = client.get("https://query1.finance.yahoo.com/v1/test/getcrumb",
                   headers=HEADERS, timeout=10)
    crumb = r.text.strip()
    if not crumb or "<" in crumb:  # HTML místo crumbu = problém
        # Zkus alternativní cestu
        r2 = client.get("https://finance.yahoo.com/quote/EURUSD=X",
                        headers=HEADERS, follow_redirects=True, timeout=10)
        r3 = client.get("https://query2.finance.yahoo.com/v1/test/getcrumb",
                        headers=HEADERS, timeout=10)
        crumb = r3.text.strip()

    return crumb, dict(client.cookies)


def _fetch_chart(symbol: str, period1: int, period2: int, interval: str = "5m") -> list[dict]:
    """Stáhne OHLCV bary z Yahoo Finance. Vrátí [{t, close}, ...]."""
    with httpx.Client(timeout=20.0, headers=HEADERS, follow_redirects=True) as client:
        try:
            crumb, _ = _get_crumb_and_cookies(client)
        except Exception as e:
            log.warning("Yahoo crumb fetch failed", error=str(e))
            crumb = ""

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        params = {
            "period1": period1,
            "period2": period2,
            "interval": interval,
            "includePrePost": "true",
            "crumb": crumb,
        }

        try:
            resp = client.get(url, params=params, timeout=15)
            if resp.status_code != 200:
                log.warning("Yahoo Finance non-200", symbol=symbol,
                            status=resp.status_code, body=resp.text[:200])
                return []
            data = resp.json()
        except Exception as e:
            log.warning("Yahoo Finance request failed", symbol=symbol, error=str(e))
            return []

    result_list = data.get("chart", {}).get("result")
    if not result_list:
        err = data.get("chart", {}).get("error")
        log.warning("Yahoo Finance chart no result", symbol=symbol, error=err)
        return []

    timestamps = result_list[0].get("timestamp", [])
    closes = result_list[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])

    bars = [
        {"t": t, "close": c}
        for t, c in zip(timestamps, closes)
        if t is not None and c is not None
    ]
    log.info("Yahoo Finance chart OK", symbol=symbol, bars=len(bars))
    return bars


def _find_close_at(bars: list[dict], target_utc: datetime, tolerance_minutes: int = 30) -> Optional[float]:
    """Z načteného seznamu barů najde Close nejblíže target_utc."""
    if not bars:
        return None
    target_epoch = target_utc.timestamp()
    tolerance_sec = tolerance_minutes * 60
    best: Optional[float] = None
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
        Stáhne celý den+1 5min barů pro daný ticker a datum.
        Jeden HTTP request (po auth) pokryje všechny zprávy z daného dne.
        """
        yahoo_sym = SYMBOL_MAP.get(ticker_symbol, ticker_symbol)
        day_start = datetime(for_date.year, for_date.month, for_date.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=2)
        period1 = int(day_start.timestamp())
        period2 = int(day_end.timestamp())
        return _fetch_chart(yahoo_sym, period1, period2, interval="5m")

    def get_prices_for_reaction(
        self, ticker_symbol: str, news_time: datetime
    ) -> dict[str, Optional[float]]:
        """Stáhne ceny kolem news_time (at, +15min, +1h, +1d)."""
        news_utc = _to_utc(news_time)
        bars = self.fetch_day_bars(ticker_symbol, news_utc.date())
        return {
            "at_news": _find_close_at(bars, news_utc),
            "15m":     _find_close_at(bars, news_utc + timedelta(minutes=15)),
            "1h":      _find_close_at(bars, news_utc + timedelta(hours=1)),
            "1d":      _find_close_at(bars, news_utc + timedelta(days=1), tolerance_minutes=60),
        }
