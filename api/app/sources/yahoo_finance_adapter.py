"""Yahoo Finance adaptér pro historická tržní data."""
from datetime import datetime, timedelta, timezone

import structlog
import yfinance as yf

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


def _to_utc(dt: datetime) -> datetime:
    """Převede naive datetime na UTC-aware (předpokládáme UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class YahooFinanceAdapter:
    """Stahuje OHLCV data pro kalibraci market reactions."""

    def get_prices_for_reaction(
        self, ticker_symbol: str, news_time: datetime
    ) -> dict[str, float | None]:
        """
        Vrátí ceny v čase zprávy, +15min, +1h a +1d.
        Používá 5min interval pro krátkodobé reakce.
        Vždy stáhne jedno volání — rozsah news_time-10min až news_time+2dny.
        """
        yahoo_sym = SYMBOL_MAP.get(ticker_symbol, ticker_symbol)
        news_utc = _to_utc(news_time)
        start = news_utc - timedelta(minutes=10)
        end = news_utc + timedelta(days=2)

        try:
            df = yf.download(
                yahoo_sym,
                start=start,
                end=end,
                interval="5m",
                progress=False,
                auto_adjust=True,
            )
        except Exception as e:
            log.warning("yfinance download failed", symbol=yahoo_sym, error=str(e))
            return {"at_news": None, "15m": None, "1h": None, "1d": None}

        if df.empty:
            log.debug("yfinance empty result", symbol=yahoo_sym, start=start, end=end)
            return {"at_news": None, "15m": None, "1h": None, "1d": None}

        # Flatten multi-level columns pokud yfinance vrátí MultiIndex
        if hasattr(df.columns, "levels"):
            df.columns = df.columns.get_level_values(0)

        # Zajistíme timezone-aware index pro srovnání
        if df.index.tzinfo is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")

        def _price_near(target: datetime) -> float | None:
            target_utc = _to_utc(target)
            try:
                # Najdi nejbližší bar PŘED nebo v čase target
                idx = df.index.searchsorted(target_utc)
                if idx >= len(df):
                    idx = len(df) - 1
                if idx < 0:
                    return None
                val = df.iloc[idx]["Close"]
                return float(val)
            except Exception as e:
                log.debug("Price lookup failed", target=target_utc, error=str(e))
                return None

        return {
            "at_news": _price_near(news_utc),
            "15m": _price_near(news_utc + timedelta(minutes=15)),
            "1h": _price_near(news_utc + timedelta(hours=1)),
            "1d": _price_near(news_utc + timedelta(days=1)),
        }
