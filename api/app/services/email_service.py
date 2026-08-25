"""Odesílání e-mailů přes Resend (HTTP API). Best-effort — chyba nikdy neshodí request.

Env: RESEND_API_KEY (povinné pro reálné odeslání), EMAIL_FROM (default noreply@tradezer.app),
APP_URL (základ pro odkazy, default https://tradezer.app).
"""
from __future__ import annotations

import os

import httpx
import structlog

log = structlog.get_logger(__name__)


def app_url() -> str:
    return os.environ.get("APP_URL", "https://tradezer.app").rstrip("/")


def _from() -> str:
    return os.environ.get("EMAIL_FROM", "Tradezer <noreply@tradezer.app>")


def send_email(to: str, subject: str, html: str) -> bool:
    key = os.environ.get("RESEND_API_KEY")
    if not key:
        log.warning("RESEND_API_KEY not set — email skipped", to=to)
        return False
    try:
        r = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"from": _from(), "to": [to], "subject": subject, "html": html},
            timeout=15.0,
        )
        if r.status_code >= 300:
            log.error("Resend send failed", status=r.status_code, body=r.text[:200])
            return False
        return True
    except Exception as e:  # noqa: BLE001
        log.error("Resend send error", error=str(e))
        return False


def reset_email_html(link: str) -> str:
    return (
        '<div style="font-family:Inter,Arial,sans-serif;max-width:480px;margin:0 auto;'
        'background:#060a0c;color:#fff;padding:32px;border-radius:12px">'
        '<h2 style="color:#60ff82;font-weight:600;margin:0 0 16px">Reset hesla</h2>'
        '<p style="color:rgba(255,255,255,0.8);line-height:1.6;font-size:15px">'
        'Někdo požádal o reset hesla k tvému účtu na tradezer.app. Klikni pro nastavení nového hesla:'
        '</p>'
        f'<p style="margin:24px 0"><a href="{link}" '
        'style="background:#60ff82;color:#06120a;font-weight:600;text-decoration:none;'
        'padding:12px 24px;border-radius:6px;display:inline-block">Nastavit nové heslo</a></p>'
        '<p style="color:rgba(255,255,255,0.5);font-size:13px">Odkaz platí 1 hodinu. '
        'Pokud jsi o reset nežádal(a), tento e-mail ignoruj.</p>'
        '</div>'
    )
