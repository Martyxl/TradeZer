"""Gamma snapshot — poslední výsledek GEX screeneru (`data/gamma_scan.py`).

Jediný řádek (name="latest") s JSON payloadem: per-instrument dealer gamma (net GEX,
regime, flip level, call/put wall, profil). Sken běží z rezidenční IP (Yahoo options
blokuje datacentra) a pushuje sem přes POST /api/gamma/ingest. Frontend čte GET /api/gamma.
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GammaSnapshot(Base):
    __tablename__ = "gamma_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
