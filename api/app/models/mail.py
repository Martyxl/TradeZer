"""Pošta info@tradezer.app pro admina — přijaté (z Resend Receiving) i odeslané zprávy.

Resend drží přijaté e-maily jen 30 dní → kopie v naší DB = trvalý archiv. Přílohy se stahují
z Resendu na požádání (odkaz platí 1 h, po 30 dnech už nejsou k dispozici).
"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MailMessage(Base):
    __tablename__ = "mail_messages"
    __table_args__ = (Index("ix_mail_folder_date", "direction", "msg_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    direction: Mapped[str] = mapped_column(String(3), nullable=False)          # in | out
    resend_id: Mapped[str | None] = mapped_column(String(64), unique=True)     # id v Resendu
    message_id: Mapped[str | None] = mapped_column(String(300), index=True)    # RFC Message-ID
    in_reply_to: Mapped[str | None] = mapped_column(String(300))
    references_hdr: Mapped[str | None] = mapped_column(Text)   # hlavička References
    thread_key: Mapped[str | None] = mapped_column(String(300), index=True)
    from_addr: Mapped[str] = mapped_column(String(320), nullable=False)
    from_name: Mapped[str | None] = mapped_column(String(200))
    to_addrs: Mapped[list | None] = mapped_column(JSON)
    cc_addrs: Mapped[list | None] = mapped_column(JSON)
    subject: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    text: Mapped[str | None] = mapped_column(Text)
    html: Mapped[str | None] = mapped_column(Text)
    attachments: Mapped[list | None] = mapped_column(JSON)                     # metadata (id, filename, size, content_type)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    msg_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
