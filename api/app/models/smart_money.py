"""Smart Money snapshot — poslední výsledek insider/congress screeneru.

Jediný řádek (name="latest") s JSON payloadem: insider Form 4 obchody + agregace
(+ později congress). Sken běží externě a pushuje sem přes POST /api/smart-money/ingest.
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SmartMoneySnapshot(Base):
    __tablename__ = "smart_money_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
