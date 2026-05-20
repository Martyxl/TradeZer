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


def _get_close_at(ticker_obj: "yf.Ticker", target_utc: datetime, window_before: int = 10, window_after: int = 10) -> float | None:
    """Stáhne 5min historii kolem target_utc a vrátí nejbližší Close."""
    start = target_utc - timedelta(minutes=window_before)
    end = target_utc + timedelta(minutes=window_after + 5)
    try:
        df = ticker_obj.history(
            start=start.strftime("%Y-%m-%d %H:%M:%S"),
            end=end.strftime("%Y-%m-%d %H:%M:%S"),
            interval="5m",
            auto_adjust=True,
            prepost=True,
        )
        if df is None or df.empty:
            return None

        # Normalize columns (MultiIndex safety)
        if hasattr(df.columns, "levels"):
            df.columns = df.columns.get_level_values(0)

        # Ensure tz-aware UTC index
        if df.index.tzinfo is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")

        idx = df.index.searchsorted(target_utc)
        idx = min(max(idx, 0), len(df) - 1)
        val = df.iloc[idx]["Close"]
        result = float(val.iloc[0] if hasattr(val, "iloc") else val)
        return result
    except Exception as e:
        log.debug("_get_close_at failed", target=str(target_utc), error=str(e))
        return None


class YahooFinanceAdapter:
    """Stahuje OHLCV data pro kalibraci market reactions."""

    def get_prices_for_reaction(
        self, ticker_symbol: str, news_time: datetime
    ) -> dict[str, float | None]:
        """
        Vrátí ceny v čase zprávy, +15min, +1h a +1d.
        Každý časový bod se stahuje samostatně (menší požadavky = vyšší spolehlivost).
        """
        yahoo_sym = SYMBOL_MAP.get(ticker_symbol, ticker_symbol)
        news_utc = _to_utc(news_time)

        try:
            t = yf.Ticker(yahoo_sym)
        except Exception as e:
            log.warning("yfinance Ticker init failed", symbol=yahoo_sym, error=str(e))
            return {"at_news": None, "15m": None, "1h": None, "1d": None}

        at_news = _get_close_at(t, news_utc, window_before=5, window_after=10)
        price_15m = _get_close_at(t, news_utc + timedelta(minutes=15))
        price_1h = _get_close_at(t, news_utc + timedelta(hours=1))
        price_1d = _get_close_at(t, news_utc + timedelta(days=1))

        log.debug(
            "yfinance prices",
            symbol=yahoo_sym,
            news_time=str(news_utc),
            at_news=at_news,
            price_15m=price_15m,
        )

        return {
            "at_news": at_news,
            "15m": price_15m,
            "1h": price_1h,
            "1d": price_1d,
        }
