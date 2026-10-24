"""Otázky do chatovacího pomocníka (vysvětluje, co Tradezer ukazuje). Odpovídá lokální model na Sparku:
web vloží otázku (queued) → Spark worker ji vyzvedne (working) a vrátí odpověď (done / error)."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class HelpChatMessage(Base):
    __tablename__ = "help_chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    page: Mapped[str] = mapped_column(String(80), nullable=False, default="/")
    question: Mapped[str] = mapped_column(Text, nullable=False)
    # Text, který uživatel právě vidí na stránce (posílá web). Po odpovědi se maže (minimalizace dat).
    context: Mapped[str | None] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="queued", index=True)  # queued|working|done|error|expired
    model: Mapped[str | None] = mapped_column(String(60))
    ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime)
