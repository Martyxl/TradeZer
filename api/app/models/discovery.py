"""Discovery snapshot — poslední výsledek momentum screeneru (`data/discovery_scan.py`).

Jediný řádek (name="latest") s JSON payloadem. Sken běží z rezidenční IP (Spark/PC,
Yahoo blokuje datacentra) a pushuje sem přes POST /api/discovery/ingest. Frontend
`/discovery` to čte přes GET /api/discovery. Malý otisk (1 řádek), žádné accumulování.
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DiscoverySnapshot(Base):
    __tablename__ = "discovery_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
