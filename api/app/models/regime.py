"""Režim trhu (klid / napětí / panika / stabilizace) — poslední výsledek `data/risk_regime.py`.

Jediný řádek (name="latest") s JSON payloadem: stav, ukazatele (VIX, S&P, ropa, zlato, výnosy),
důvody a LLM hodnocení závažnosti světových titulků. Sken běží na Sparku a pushuje sem přes
POST /api/regime/ingest, frontend a fond čtou GET /api/regime.
"""
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RegimeSnapshot(Base):
    __tablename__ = "regime_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
