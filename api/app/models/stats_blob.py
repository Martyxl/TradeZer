"""Předpočítané market statistiky (Stats/ORB) — JSON blob na klíč, publikuje Spark.

name = "<kind>:<key>", např. "stats:nq", "orb:eurusd". Spark (`data/publish_stats.py`) po přepočtu
`compute_stats.py` nahraje každý soubor přes PUT /api/marketstats/{kind}/{key}; web čte z DB
a při chybějícím blobu spadne na statický JSON z repa.
"""
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MarketStatsBlob(Base):
    __tablename__ = "market_stats_blobs"

    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
