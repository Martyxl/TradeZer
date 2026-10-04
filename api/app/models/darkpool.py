"""Dark Pool snapshot — poslední FINRA ATS (off-exchange) týdenní objemy per symbol.

Jediný řádek (name="latest") s JSON payloadem (top symboly dle ATS objemu/notional).
Sken `data/finra_darkpool_scan.py` běží externě a pushuje přes POST /api/darkpool/ingest.
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DarkPoolSnapshot(Base):
    __tablename__ = "darkpool_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
