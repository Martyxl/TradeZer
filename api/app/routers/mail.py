"""Admin pošta (info@tradezer.app) — jedno místo pro čtení a odpovídání. Jen pro admina.

GET  /api/admin/mail?folder=in|out&q=         seznam (bez těla)
POST /api/admin/mail/sync                      stáhne nové přijaté zprávy z Resendu do DB
GET  /api/admin/mail/{id}                      celá zpráva (označí přečtenou) + vlákno
POST /api/admin/mail/{id}/read                 {read: bool}
GET  /api/admin/mail/{id}/attachments/{att}    {url} = dočasný odkaz Resendu ke stažení (platí 1 h)
POST /api/admin/mail/send                      {to, cc?, subject, text, reply_to_id?}

Resend Receiving: list GET /emails/receiving, detail GET /emails/receiving/{id} (webhook nepotřebujeme —
synchronizace při otevření schránky). Odpověď ve vlákně = hlavičky In-Reply-To / References.
"""
from __future__ import annotations

import html as html_lib
import os
import re
from datetime import datetime
from email.utils import parseaddr

import httpx
import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.mail import MailMessage
from app.models.user import User
from app.routers.auth import require_admin

router = APIRouter(prefix="/api/admin/mail", tags=["mail"])
log = structlog.get_logger(__name__)

RESEND = "https://api.resend.com"
SYNC_MAX = 200
_EMAIL_RE = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")


def _key() -> str:
    key = (os.environ.get("RESEND_API_KEY") or "").strip()
    if not key:
        raise HTTPException(status_code=503, detail="RESEND_API_KEY není nastavený")
    return key


def _mail_from() -> str:
    return os.environ.get("MAIL_FROM", "Tradezer <info@tradezer.app>").strip()


async def _resend(method: str, path: str, **kw) -> dict:
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.request(method, RESEND + path, headers={"Authorization": f"Bearer {_key()}"}, **kw)
    if r.status_code in (401, 403):
        raise HTTPException(status_code=502, detail="Resend odmítl klíč — pro příjem pošty je potřeba API klíč s plným přístupem")
    if r.status_code >= 300:
        raise HTTPException(status_code=502, detail=f"Resend vrátil {r.status_code}: {r.text[:200]}")
    return r.json()


def _parse_dt(s: str | None) -> datetime:
    if not s:
        return datetime.utcnow()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T", 1)).replace(tzinfo=None)
    except ValueError:
        return datetime.utcnow()


def _hdr(headers: dict | None, name: str) -> str | None:
    if not isinstance(headers, dict):
        return None
    for k, v in headers.items():
        if k.lower() == name:
            return v if isinstance(v, str) else (v[0] if isinstance(v, list) and v else None)
    return None


def _thread_key(message_id: str | None, in_reply_to: str | None, references: str | None) -> str | None:
    refs = (references or "").split()
    return refs[0] if refs else (in_reply_to or message_id)


def _summary(m: MailMessage) -> dict:
    snippet = re.sub(r"\s+", " ", (m.text or re.sub(r"<[^>]+>", " ", m.html or ""))).strip()[:140]
    return {"id": m.id, "direction": m.direction, "from_addr": m.from_addr, "from_name": m.from_name,
            "to": m.to_addrs or [], "subject": m.subject, "snippet": snippet, "date": m.msg_date.isoformat(),
            "is_read": m.is_read, "has_attachments": bool(m.attachments)}


@router.get("")
async def list_mail(folder: str = Query("in", pattern="^(in|out)$"), q: str | None = Query(None, max_length=100),
                    _: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    stmt = select(MailMessage).where(MailMessage.direction == folder)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(MailMessage.subject.ilike(like), MailMessage.from_addr.ilike(like),
                              MailMessage.text.ilike(like)))
    rows = (await session.execute(stmt.order_by(MailMessage.msg_date.desc()).limit(200))).scalars().all()
    unread = (await session.execute(select(MailMessage.id).where(
        MailMessage.direction == "in", MailMessage.is_read.is_(False)))).all()
    return {"items": [_summary(m) for m in rows], "unread": len(unread)}


@router.post("/sync")
async def sync(_: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    """Stáhne přijaté zprávy, které ještě nemáme (Resend je řadí od nejnovější)."""
    known = set((await session.execute(select(MailMessage.resend_id).where(MailMessage.resend_id.isnot(None)))).scalars())
    new_ids: list[str] = []
    after = None
    while len(new_ids) < SYNC_MAX:
        params = {"limit": 50, **({"after": after} if after else {})}
        page = await _resend("GET", "/emails/receiving", params=params)
        data = page.get("data") or []
        fresh = [d["id"] for d in data if d.get("id") and d["id"] not in known]
        new_ids += fresh
        if not page.get("has_more") or not data or len(fresh) < len(data):
            break   # narazili jsme na už uložené → starší máme taky
        after = data[-1]["id"]
    added = 0
    for rid in reversed(new_ids):   # od nejstarší, ať jsou ID v DB chronologicky
        d = await _resend("GET", f"/emails/receiving/{rid}")
        headers = d.get("headers") or {}
        name, addr = parseaddr(_hdr(headers, "from") or d.get("from") or "")
        mid = d.get("message_id")
        irt = _hdr(headers, "in-reply-to")
        refs = _hdr(headers, "references")
        session.add(MailMessage(
            direction="in", resend_id=rid, message_id=mid, in_reply_to=irt, references_hdr=refs,
            thread_key=_thread_key(mid, irt, refs), from_addr=(addr or d.get("from") or "?")[:320],
            from_name=(name or None) and name[:200], to_addrs=d.get("to") or [], cc_addrs=d.get("cc") or [],
            subject=(d.get("subject") or "")[:500], text=d.get("text"), html=d.get("html"),
            attachments=[{k: a.get(k) for k in ("id", "filename", "size", "content_type")}
                         for a in (d.get("attachments") or [])],
            msg_date=_parse_dt(d.get("created_at")), is_read=False))
        added += 1
    await session.commit()
    log.info("Mail sync", added=added)
    return {"added": added}


@router.get("/{mail_id}")
async def get_mail(mail_id: int, _: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    m = await session.get(MailMessage, mail_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Zpráva nenalezena")
    if not m.is_read:
        m.is_read = True
        await session.commit()
    thread = []
    if m.thread_key:
        rows = (await session.execute(select(MailMessage).where(MailMessage.thread_key == m.thread_key)
                                      .order_by(MailMessage.msg_date))).scalars().all()
        thread = [_summary(t) for t in rows if t.id != m.id]
    return {**_summary(m), "cc": m.cc_addrs or [], "text": m.text, "html": m.html,
            "attachments": m.attachments or [], "message_id": m.message_id, "thread": thread}


@router.post("/{mail_id}/read")
async def set_read(mail_id: int, payload: dict = Body(...), _: User = Depends(require_admin),
                   session: AsyncSession = Depends(get_session)):
    m = await session.get(MailMessage, mail_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Zpráva nenalezena")
    m.is_read = bool(payload.get("read", True))
    await session.commit()
    return {"status": "ok"}


@router.get("/{mail_id}/attachments/{att_id}")
async def attachment(mail_id: int, att_id: str, _: User = Depends(require_admin),
                     session: AsyncSession = Depends(get_session)):
    m = await session.get(MailMessage, mail_id)
    if m is None or not m.resend_id or not any(a.get("id") == att_id for a in (m.attachments or [])):
        raise HTTPException(status_code=404, detail="Příloha nenalezena")
    page = await _resend("GET", f"/emails/receiving/{m.resend_id}/attachments")
    for a in page.get("data") or []:
        if a.get("id") == att_id and a.get("download_url"):
            return {"url": a["download_url"], "filename": a.get("filename"), "expires_at": a.get("expires_at")}
    raise HTTPException(status_code=410, detail="Příloha už v Resendu není (uchovávají 30 dní)")


def _addr_list(v) -> list[str]:
    items = v if isinstance(v, list) else re.split(r"[,;]\s*", v or "")
    out = [x.strip() for x in items if x and x.strip()]
    bad = [x for x in out if not _EMAIL_RE.match(parseaddr(x)[1] or "")]
    if bad:
        raise HTTPException(status_code=422, detail=f"Neplatná adresa: {', '.join(bad)}")
    return out


@router.post("/send")
async def send(payload: dict = Body(...), _: User = Depends(require_admin),
               session: AsyncSession = Depends(get_session)):
    to = _addr_list(payload.get("to"))
    cc = _addr_list(payload.get("cc"))
    if not to:
        raise HTTPException(status_code=422, detail="Chybí příjemce")
    if len(to) + len(cc) > 20:
        raise HTTPException(status_code=422, detail="Max 20 příjemců")
    subject = (payload.get("subject") or "").strip()[:500]
    text = (payload.get("text") or "").strip()
    if not subject or not text:
        raise HTTPException(status_code=422, detail="Chybí předmět nebo text")
    headers: dict[str, str] = {}
    parent = None
    if payload.get("reply_to_id"):
        parent = await session.get(MailMessage, int(payload["reply_to_id"]))
        if parent and parent.message_id:
            headers["In-Reply-To"] = parent.message_id
            headers["References"] = " ".join(x for x in [parent.references_hdr, parent.message_id] if x)
    body_html = ('<div style="font-family:Arial,sans-serif;font-size:14px;line-height:1.5;white-space:pre-wrap">'
                 + html_lib.escape(text) + "</div>")
    sent = await _resend("POST", "/emails", json={
        "from": _mail_from(), "to": to, **({"cc": cc} if cc else {}), "subject": subject,
        "text": text, "html": body_html, **({"headers": headers} if headers else {})})
    name, addr = parseaddr(_mail_from())
    msg = MailMessage(direction="out", resend_id=sent.get("id"), from_addr=addr, from_name=name or None,
                      to_addrs=to, cc_addrs=cc, subject=subject, text=text, html=None,
                      in_reply_to=headers.get("In-Reply-To"), references_hdr=headers.get("References"),
                      thread_key=(parent.thread_key or parent.message_id) if parent else None,
                      is_read=True, msg_date=datetime.utcnow())
    session.add(msg)
    await session.commit()
    return {"status": "sent", "id": msg.id, "resend_id": sent.get("id")}
