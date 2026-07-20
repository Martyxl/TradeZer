"""Seed script — zakládá jen strukturální data (tickery, zdroje, kategorie)."""
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import session_context
from app.db.engine import engine
from app.db.base import Base
from app.models import Ticker, NewsSource, NewsCategory


TICKERS = [
    {"symbol": "EURUSD", "name": "EUR/USD",          "asset_class": "forex",    "source_symbol_map": {"yahoo": "EURUSD=X", "cme": "6E"}, "neutral_threshold": 0.002, "enabled": True},
    {"symbol": "GBPUSD", "name": "GBP/USD",          "asset_class": "forex",    "source_symbol_map": {"yahoo": "GBPUSD=X"},              "neutral_threshold": 0.002, "enabled": False},
    {"symbol": "USDJPY", "name": "USD/JPY",          "asset_class": "forex",    "source_symbol_map": {"yahoo": "USDJPY=X"},              "neutral_threshold": 0.002, "enabled": False},
    {"symbol": "XAUUSD", "name": "XAU/USD",          "asset_class": "commodity","source_symbol_map": {"yahoo": "GC=F"},                  "neutral_threshold": 0.002, "enabled": True},
    {"symbol": "BTCUSD", "name": "BTC/USD",          "asset_class": "crypto",   "source_symbol_map": {"yahoo": "BTC-USD"},               "neutral_threshold": 0.005, "enabled": True},
    {"symbol": "ES",     "name": "E-mini S&P 500",   "asset_class": "futures",  "source_symbol_map": {"yahoo": "ES=F", "cme": "ES"},     "neutral_threshold": 0.002, "enabled": True},
    {"symbol": "NQ",     "name": "E-mini Nasdaq 100","asset_class": "futures",  "source_symbol_map": {"yahoo": "NQ=F", "cme": "NQ"},     "neutral_threshold": 0.003, "enabled": True},
    {"symbol": "YM",     "name": "E-mini Dow Jones", "asset_class": "futures",  "source_symbol_map": {"yahoo": "YM=F", "cme": "YM"},     "neutral_threshold": 0.0008, "enabled": True},
]

NEWS_SOURCES = [
    {"name": "forex_factory",     "source_weight": 1.0, "config": {"url": "https://www.forexfactory.com/ff_calendar_thisweek.xml"}},
    {"name": "newsapi",           "source_weight": 0.7, "config": {"base_url": "https://newsapi.org/v2/everything"}},
    {"name": "finnhub",           "source_weight": 0.6, "config": {"base_url": "https://finnhub.io/api/v1"}},
    {"name": "alphavantage",      "source_weight": 0.6, "config": {"base_url": "https://www.alphavantage.co/query"}},
    {"name": "rss_reuters",       "source_weight": 0.5, "config": {"url": "https://feeds.reuters.com/reuters/businessNews"}},
    {"name": "rss_ecb",           "source_weight": 0.9, "config": {"url": "https://www.ecb.europa.eu/rss/press.html"}},
    {"name": "rss_fxstreet_gold", "source_weight": 0.75, "config": {"url": "https://www.fxstreet.com/rss/analysis/commodities", "instruments_hint": ["XAUUSD"]}},
    {"name": "rss_mining",        "source_weight": 0.65, "config": {"url": "https://www.mining.com/feed/", "instruments_hint": ["XAUUSD"]}},
    {"name": "rss_cnbc_markets",  "source_weight": 0.75, "config": {"url": "https://www.cnbc.com/id/20910258/device/rss/rss.html", "instruments_hint": ["ES"]}},
    {"name": "rss_cnbc_tech",     "source_weight": 0.70, "config": {"url": "https://www.cnbc.com/id/19854910/device/rss/rss.html", "instruments_hint": ["NQ"]}},
]

CATEGORIES = [
    ("monetary_policy",    "Rozhodnutí centrálních bank o úrokových sazbách"),
    ("inflation",          "Data o inflaci (CPI, PPI, PCE)"),
    ("employment",         "Pracovní trh (NFP, unemployment, ADP)"),
    ("gdp",                "HDP a ekonomický růst"),
    ("trade_balance",      "Obchodní bilance a platební bilance"),
    ("geopolitical",       "Geopolitické události a konflikty"),
    ("ecb_speech",         "Projevy a komunikace ECB"),
    ("fed_speech",         "Projevy a komunikace Fedu"),
    ("pmi",                "PMI indexy (výroba, služby)"),
    ("retail_sales",       "Maloobchodní tržby"),
    ("housing",            "Realitní trh a stavebnictví"),
    ("consumer_confidence","Spotřebitelská důvěra"),
    ("energy",             "Energetické ceny a zásoby"),
    ("earnings",           "Firemní výsledky"),
    ("risk_sentiment",     "Obecný sentiment na trzích"),
    ("fiscal_policy",      "Fiskální politika a vládní výdaje"),
    ("technical_breakout", "Technické prolomení důležitých levelů"),
    ("surprise_beat",      "Výrazně lepší data než očekávání"),
    ("surprise_miss",      "Výrazně horší data než očekávání"),
    ("central_bank_minutes","Minuty ze zasedání centrálních bank"),
    ("safe_haven",         "Bezpečné přístave — zlato, dluhopisy"),
    ("equity_index",       "Akciové indexy a sentiment"),
    ("tech_sector",        "Technologický sektor"),
]


async def seed(session: AsyncSession) -> None:
    print("Seeding tickers...")
    for t in TICKERS:
        existing = await session.scalar(select(Ticker).where(Ticker.symbol == t["symbol"]))
        if not existing:
            session.add(Ticker(**t))
        else:
            existing.enabled = t["enabled"]
            existing.neutral_threshold = t["neutral_threshold"]

    print("Seeding news sources...")
    for s in NEWS_SOURCES:
        existing = await session.scalar(select(NewsSource).where(NewsSource.name == s["name"]))
        if not existing:
            session.add(NewsSource(**s))

    print("Seeding categories...")
    for name, desc in CATEGORIES:
        existing = await session.scalar(select(NewsCategory).where(NewsCategory.name == name))
        if not existing:
            session.add(NewsCategory(name=name, description=desc))

    await session.commit()
    print("Seed dokoncen — strukturalni data pripravena.")
    print("Spust refresh: POST /api/refresh pro nacteni realnych zprav.")


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_context() as session:
        await seed(session)


if __name__ == "__main__":
    asyncio.run(main())
