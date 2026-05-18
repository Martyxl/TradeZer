"""Yahoo Finance adaptér pro historická tržní data."""
from datetime import datetime, timedelta

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


class YahooFinanceAdapter:
    """Stahuje OHLCV data pro kalibraci market reactions."""

    def get_price_at(self, ticker_symbol: str, at: datetime) -> float | None:
        yahoo_sym = SYMBOL_MAP.get(ticker_symbol, ticker_symbol)
        start = at - timedelta(minutes=5)
        end = at + timedelta(minutes=30)
        try:
            df = yf.download(yahoo_sym, start=start, end=end, interval="5m", progress=False)
            if df.empty:
                return None
            closest = df.index.asof(at) if hasattr(df.index, "asof") else df.index[0]
            return float(df.loc[closest]["Close"].iloc[0] if hasattr(df.loc[closest]["Close"], "iloc") else df.loc[closest]["Close"])
        except Exception as e:
            log.warning("Yahoo Finance price fetch failed", symbol=yahoo_sym, error=str(e))
            return None

    def get_prices_for_reaction(
        self, ticker_symbol: str, news_time: datetime
    ) -> dict[str, float | None]:
        yahoo_sym = SYMBOL_MAP.get(ticker_symbol, ticker_symbol)
        end = news_time + timedelta(days=2)
        start = news_time - timedelta(minutes=10)
        try:
            df = yf.download(yahoo_sym, start=start, end=end, interval="5m", progress=False)
            if df.empty:
                return {"at_news": None, "15m": None, "1h": None, "1d": None}

            def _price_near(target: datetime) -> float | None:
                try:
                    idx = df.index.searchsorted(target)
                    idx = min(idx, len(df) - 1)
                    val = df.iloc[idx]["Close"]
                    return float(val.iloc[0] if hasattr(val, "iloc") else val)
                except Exception:
                    return None

            return {
                "at_news": _price_near(news_time),
                "15m": _price_near(news_time + timedelta(minutes=15)),
                "1h": _price_near(news_time + timedelta(hours=1)),
                "1d": _price_near(news_time + timedelta(days=1)),
            }
        except Exception as e:
            log.warning("Yahoo Finance OHLCV failed", symbol=yahoo_sym, error=str(e))
            return {"at_news": None, "15m": None, "1h": None, "1d": None}
