"""E-mailová upozornění na výsledky hospodaření (odběr si zapíná uživatel v radaru).

Kdy se posílá: hned jak Spark výsledky vysvětlí (ingest s analýzou). „Kritické“ = stejné pravidlo jako
žlutý vykřičník v radaru (web/components/valuation/EarningsReports.tsx → earningsAlerts): verdikt není
neutrální, nebo akcie od zveřejnění pohnula o ≥ 3 %. Neutrální report, u kterého akcie až později výrazně
pohne, odejde odběratelům „jen kritické“ až z reakce. Každý report jde uživateli nejvýš jednou.
"""
from __future__ import annotations

import asyncio
import html
import secrets
from datetime import datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.valuation.models import ValEarningsAlertSent, ValEarningsAlertSub, ValEarningsReport

log = structlog.get_logger(__name__)

ALERT_DAYS = 7
ALERT_MOVE_PCT = 3.0
SCOPES = ("all", "portfolio", "custom")
MAX_TICKERS = 50
VERDICT_CS = {"positive": ("Pozitivní", "#4ade80"), "negative": ("Negativní", "#f87171"),
              "mixed": ("Smíšené", "#eab308"), "neutral": ("Neutrální", "#9ca3af")}


def is_critical(r: ValEarningsReport) -> bool:
    if datetime.utcnow() - r.accepted_at > timedelta(days=ALERT_DAYS):
        return False
    moved = r.reaction_pct is not None and abs(r.reaction_pct) >= ALERT_MOVE_PCT
    return moved or (r.verdict is not None and r.verdict != "neutral")


def new_token() -> str:
    return secrets.token_urlsafe(32)


def sub_out(s: ValEarningsAlertSub | None, email: str | None) -> dict:
    return {"enabled": bool(s and s.enabled), "scope": s.scope if s else "all",
            "tickers": (s.tickers or []) if s else [], "only_critical": s.only_critical if s else True,
            "email": email}


def _wanted(s: ValEarningsAlertSub, ticker: str, held: set[str] | None) -> bool:
    if s.scope == "portfolio":
        return held is not None and ticker in held
    if s.scope == "custom":
        return ticker in {t.upper() for t in (s.tickers or [])}
    return True


def _fmt(v: float | None, d: int = 2) -> str:
    return "—" if v is None else f"{v:,.{d}f}".replace(",", " ").replace(".", ",")


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{'+' if v > 0 else ''}{_fmt(v, 1)} %"


def email_html(r: ValEarningsReport, name: str | None, base: str, unsubscribe: str) -> str:
    e = html.escape
    label, color = VERDICT_CS.get(r.verdict or "", ("Bez hodnocení", "#9ca3af"))
    rev = "—" if r.revenue is None else (f"{_fmt(r.revenue / 1e9, 1)} mld USD" if r.revenue >= 1e9
                                         else f"{_fmt(r.revenue / 1e6, 0)} mil USD")
    eps = f"{_fmt(r.eps_actual)} USD" + (f" (odhad {_fmt(r.eps_estimate)})" if r.eps_estimate is not None else "")
    bullets = "".join(f'<li style="margin:0 0 6px">{e(ln.lstrip("-• ").strip())}</li>'
                      for ln in (r.summary_cs or "").splitlines() if ln.strip())
    cell = 'style="padding:8px 10px;background:#0f1117;border-radius:6px;font-size:13px;color:#e5e7eb"'
    small = 'style="display:block;font-size:10px;color:#6b7280;text-transform:uppercase;letter-spacing:.05em"'
    link = f"{base}/valuation?ticker={e(r.ticker)}"
    return (
        '<div style="font-family:Inter,Arial,sans-serif;max-width:560px;margin:0 auto;background:#060a0c;'
        'color:#fff;padding:28px;border-radius:12px">'
        f'<div style="font-size:12px;color:#6b7280">Výsledky hospodaření · {e(r.fiscal_period or "")}</div>'
        f'<h2 style="margin:4px 0 8px;font-size:20px">{e(r.ticker)} <span style="font-weight:400;color:#9ca3af;'
        f'font-size:15px">{e(name or "")}</span></h2>'
        f'<span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:600;'
        f'background:{color}22;color:{color}">{label}</span>'
        + (f' <span style="font-size:12px;color:#9ca3af">akcie od zveřejnění {_pct(r.reaction_pct)}</span>'
           if r.reaction_pct is not None else "")
        + f'<p style="font-size:15px;line-height:1.5;color:#e5e7eb;margin:14px 0">{e(r.headline_cs or "")}</p>'
        '<table style="width:100%;border-spacing:6px;margin:0 -6px"><tr>'
        f'<td {cell}><span {small}>Tržby</span>{rev}<br><span style="font-size:11px;color:#9ca3af">'
        f'{_pct(r.revenue_yoy_pct)} meziročně</span></td>'
        f'<td {cell}><span {small}>Zisk na akcii</span>{eps}<br><span style="font-size:11px;color:#9ca3af">'
        f'{_pct(r.eps_surprise_pct)} vs. odhad</span></td></tr></table>'
        + (f'<div style="margin:16px 0 6px;font-size:13px;font-weight:600">Co to znamená pro firmu</div>'
           f'<ul style="padding-left:18px;margin:0;font-size:13px;line-height:1.5;color:#d1d5db">{bullets}</ul>'
           if bullets else "")
        + (f'<p style="font-size:13px;color:#d1d5db;line-height:1.5"><b>Výhled vedení:</b> {e(r.guidance_cs)}</p>'
           if r.guidance_cs else "")
        + f'<p style="margin:22px 0"><a href="{link}" style="background:#60ff82;color:#06120a;font-weight:600;'
        'text-decoration:none;padding:10px 20px;border-radius:6px;display:inline-block">Otevřít v radaru</a></p>'
        '<p style="font-size:12px;color:#6b7280;line-height:1.5">Vysvětlení napsala AI z tiskové zprávy (SEC) a '
        'konsenzu analytiků; proč trh reaguje doplníme v radaru zhruba 45 minut po zveřejnění. '
        'Není to investiční doporučení.</p>'
        f'<p style="font-size:11px;color:#4b5563">Tento e-mail dostáváš, protože máš v Tradezeru zapnutá upozornění '
        f'na výsledky hospodaření. <a href="{unsubscribe}" style="color:#6b7280">Odhlásit odběr</a></p>'
        '</div>'
    )


async def notify(session: AsyncSession, r: ValEarningsReport, name: str | None, *,
                 only_user_id: int | None = None, force: bool = False) -> int:
    """Pošle report odběratelům, kterým ještě neodešel. force = zkušební e-mail (bez kontrol a záznamu)."""
    from app.models import User
    from app.routers.auth import plan_rank
    from app.routers.valuation import _held_tickers
    from app.services.email_service import app_url, send_batch
    from app.config import settings
    if not r.headline_cs:
        return 0
    critical = is_critical(r)
    q = (select(ValEarningsAlertSub, User).join(User, User.id == ValEarningsAlertSub.user_id)
         .where(User.email.isnot(None)))
    if only_user_id is not None:
        q = q.where(ValEarningsAlertSub.user_id == only_user_id)
    else:
        q = q.where(ValEarningsAlertSub.enabled.is_(True))
    rows = (await session.execute(q)).all()
    already = set((await session.execute(select(ValEarningsAlertSent.user_id)
                                         .where(ValEarningsAlertSent.report_id == r.id))).scalars())
    base = app_url()
    msgs, recips = [], {}
    for s, u in rows:
        if not force:
            if u.id in already or (s.only_critical and not critical):
                continue
            if settings.paywall_enabled and not u.is_admin and plan_rank(u.plan) < plan_rank("trader"):
                continue
            held = await _held_tickers(session, u.id) if s.scope == "portfolio" else None
            if not _wanted(s, r.ticker, held):
                continue
        unsub = f"{base}/api/valuation/earnings/alerts/unsubscribe?token={s.unsubscribe_token}"
        label = VERDICT_CS.get(r.verdict or "", ("", ""))[0]
        msgs.append({"to": u.email, "html": email_html(r, name, base, unsub),
                     "subject": f"{r.ticker}: výsledky {r.fiscal_period or ''} — {label.lower() or 'nové'}".replace("  ", " "),
                     "headers": {"List-Unsubscribe": f"<{unsub}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}})
        recips[u.email] = u.id
    if not msgs:
        return 0
    sent = await asyncio.to_thread(send_batch, msgs)
    if not force:
        for addr in sent:
            session.add(ValEarningsAlertSent(user_id=recips[addr], report_id=r.id))
        await session.commit()
    log.info("Earnings alerts sent", ticker=r.ticker, report=r.id, n=len(sent), critical=critical)
    return len(sent)
