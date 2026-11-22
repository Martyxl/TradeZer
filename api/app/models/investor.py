"""Profil investora pro jednoduchý režim (Začátečník): zvolený režim UI, investiční plán
(cílové rozložení), měsíční vklad a rezerva mimo brokera. Jeden řádek na uživatele."""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class InvestorProfile(Base):
    __tablename__ = "investor_profiles"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    mode: Mapped[str | None] = mapped_column(String(10))          # simple | pro | None = ještě nevybral
    plan: Mapped[str] = mapped_column(String(16), default="balanced", nullable=False)  # careful|balanced|bold|custom
    targets: Mapped[dict | None] = mapped_column(JSON)            # jen u plan=custom: {třída: %}
    monthly_czk: Mapped[float] = mapped_column(Float, default=5000, nullable=False)
    reserve_czk: Mapped[float] = mapped_column(Float, default=0, nullable=False)  # hotovost / spořicí účet mimo brokera
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
