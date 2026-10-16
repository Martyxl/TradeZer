"""Kontrola zdrojů zpráv — živá zkouška feedů (z prostředí, kde backend běží = IP Vercelu, odkud
řada webů blokuje) + přehled, kolik zpráv který zdroj skutečně dodal do databáze.

Důvod: zdroje umírají potichu (FXStreet 403, Reuters feed zanikl) a nikdo si toho nevšimne, dokud
dashboard nezestárne. `/api/sources/check` a `/api/sources/health` (token) to dělají viditelné.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import feedparser
import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Tradezer/1.0; RSS reader)"}


def _newest(feed) -> str | None:
    best = None
    for e in feed.entries:
        for attr in ("published", "updated"):
            v = getattr(e, attr, None)
            if not v:
                continue
            try:
                d = parsedate_to_datetime(v)
                d = d.astimezone(timezone.utc) if d.tzinfo else d.replace(tzinfo=timezone.utc)
                if best is None or d > best:
                    best = d
                break
            except (TypeError, ValueError):
                continue
    return best.isoformat(timespec="minutes") if best else None


async def probe_feed(client: httpx.AsyncClient, url: str) -> dict:
    """Jedna zkouška feedu: HTTP status, počet položek, stáří nejnovější. `ok` = 200 a aspoň 1 položka."""
    t0 = time.monotonic()
    try:
        r = await client.get(url)
        out = {"url": url, "status": r.status_code, "ms": int((time.monotonic() - t0) * 1000),
               "entries": 0, "newest": None, "ok": False}
        if r.status_code == 200:
            feed = feedparser.parse(r.text)
            out["entries"] = len(feed.entries)
            out["newest"] = _newest(feed)
            out["ok"] = out["entries"] > 0
            out["title"] = (feed.feed.get("title") or "")[:80] if hasattr(feed, "feed") else ""
        return out
    except Exception as e:  # noqa: BLE001
        return {"url": url, "status": 0, "ms": int((time.monotonic() - t0) * 1000), "entries": 0,
                "newest": None, "ok": False, "error": type(e).__name__}


async def probe_many(urls: list[str], client: httpx.AsyncClient | None = None) -> list[dict]:
    own = client is None
    client = client or httpx.AsyncClient(timeout=15.0, headers=HEADERS, follow_redirects=True)
    try:
        return list(await asyncio.gather(*[probe_feed(client, u) for u in urls]))
    finally:
        if own:
            await client.aclose()


async def db_activity(session: AsyncSession, hours: int = 24) -> list[dict]:
    """Kolik zpráv každý zdroj uložil za posledních N hodin + kdy naposledy."""
    from app.models import NewsItem, NewsSource
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    rows = (await session.execute(
        select(NewsSource.name,
               func.count(NewsItem.id).filter(NewsItem.fetched_at >= cutoff),
               func.max(NewsItem.fetched_at))
        .join(NewsItem, NewsItem.source_id == NewsSource.id, isouter=True)
        .group_by(NewsSource.name).order_by(NewsSource.name)
    )).all()
    return [{"source": n, f"stored_last_{hours}h": int(c or 0),
             "last_stored": last.isoformat(timespec="minutes") if last else None} for n, c, last in rows]
