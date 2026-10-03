"""Investorský deník — portfolio transakce (per-user) + živé ceny.

Oddělené od trading deníku (journal). Dashboard počítá holdings z transakcí
(průměrná cena), živá hodnota přes InvestmentQuote (ceny + FX pushnuté z PC/Sparku,
protože Yahoo nejde z Vercelu). Import z brokerů (XTB/eToro/…) normalizuje do TxType.
"""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class InvestmentTx(Base):
    __tablename__ = "investment_tx"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    broker: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)  # xtb|etoro|trading212|portu|manual
    tx_type: Mapped[str] = mapped_column(String(16), nullable=False)  # buy|sell|dividend|fee|deposit|withdrawal
    symbol: Mapped[str | None] = mapped_column(String(40), index=True)  # ticker (AAPL), None u deposit/fee
    name: Mapped[str | None] = mapped_column(String(120))
    quantity: Mapped[float | None] = mapped_column(Float)
    price: Mapped[float | None] = mapped_column(Float)      # cena za kus v currency
    currency: Mapped[str] = mapped_column(String(8), default="USD", nullable=False)
    fee: Mapped[float | None] = mapped_column(Float)
    amount: Mapped[float | None] = mapped_column(Float)     # celková částka (dividenda/vklad)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(60))  # import batch / název souboru
    dedup_hash: Mapped[str | None] = mapped_column(String(64), index=True)  # proti duplicitám při importu
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())


class InvestmentQuote(Base):
    """Živá cena symbolu (nebo FX páru jako 'USDCZK'). Upsert dle symbol — držíme
    jen poslední hodnotu. Plní se push endpointem z rezidenční IP (Yahoo)."""
    __tablename__ = "investment_quotes"

    symbol: Mapped[str] = mapped_column(String(40), primary_key=True)  # AAPL | USDCZK | EURCZK
    price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str | None] = mapped_column(String(8))
    high_52w: Mapped[float | None] = mapped_column(Float)   # pro semafor (poloha v rozpětí)
    low_52w: Mapped[float | None] = mapped_column(Float)
    as_of: Mapped[datetime | None] = mapped_column(DateTime)
    source: Mapped[str | None] = mapped_column(String(40))
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
