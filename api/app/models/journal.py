"""Obchodní deník — záznamy obchodů uživatele (per-user) + poznámky.

MVP: ruční zápis. Screenshot přes URL (bez blob úložiště). Výsledek se drží
v R (r_result) i volitelně v P/L; win/loss se odvozuje z r_result, jinak z pnl.
"""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    instrument: Mapped[str] = mapped_column(String(40), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # long | short
    entry_price: Mapped[float | None] = mapped_column(Float)
    exit_price: Mapped[float | None] = mapped_column(Float)
    size: Mapped[float | None] = mapped_column(Float)
    r_result: Mapped[float | None] = mapped_column(Float)   # výsledek v R (násobek rizika)
    pnl: Mapped[float | None] = mapped_column(Float)        # P/L v bodech/měně
    traded_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)  # kdy obchod proběhl
    session: Mapped[str | None] = mapped_column(String(20))   # asia | london | ny | other
    setup: Mapped[str | None] = mapped_column(String(80))     # tag setupu (např. "ORB London")
    notes: Mapped[str | None] = mapped_column(Text)
    screenshot_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())


class JournalAnalysisJob(Base):
    """Async job pro AI vision extrakci obchodu (engine=spark). Claude engine běží
    synchronně a job nepotřebuje. Spark worker (na Sparku) polluje pending, stáhne
    obrázek ze source_url, proežene lokální vision model a pushne result zpět."""
    __tablename__ = "journal_analysis_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    engine: Mapped[str] = mapped_column(String(20), default="spark", nullable=False)  # claude | spark
    source_url: Mapped[str | None] = mapped_column(String(500))  # TradingView URL (worker stáhne obrázek)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)  # pending|done|failed
    result: Mapped[str | None] = mapped_column(Text)   # JSON s vytěženými poli
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())
