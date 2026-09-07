"""Obchodní deník — CRUD záznamů + souhrnná statistika. Vše per-user (Bearer token).

MVP: ruční zápis. Vlastnictví se hlídá přes user_id z tokenu (current_user);
uživatel nikdy nevidí ani nemění cizí záznamy.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import User
from app.models.journal import JournalEntry
from app.routers.auth import current_user

router = APIRouter(prefix="/api/journal", tags=["journal"])

DIRECTIONS = {"long", "short"}
SESSIONS = {"asia", "london", "ny", "other"}


def _out(e: JournalEntry) -> dict:
    return {
        "id": e.id,
        "instrument": e.instrument,
        "direction": e.direction,
        "entry_price": e.entry_price,
        "exit_price": e.exit_price,
        "size": e.size,
        "r_result": e.r_result,
        "pnl": e.pnl,
        "traded_at": e.traded_at.isoformat() if e.traded_at else None,
        "session": e.session,
        "setup": e.setup,
        "notes": e.notes,
        "screenshot_url": e.screenshot_url,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def _parse_dt(v) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


def _num(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _apply(e: JournalEntry, p: dict) -> None:
    """Zapíše validovaná pole z payloadu do záznamu (create i update)."""
    if "instrument" in p:
        e.instrument = (str(p.get("instrument") or "").strip() or "?")[:40]
    if "direction" in p:
        d = str(p.get("direction") or "").lower().strip()
        e.direction = d if d in DIRECTIONS else "long"
    if "session" in p:
        s = str(p.get("session") or "").lower().strip()
        e.session = s if s in SESSIONS else None
    if "setup" in p:
        e.setup = (str(p.get("setup")).strip()[:80] or None) if p.get("setup") else None
    if "notes" in p:
        e.notes = str(p.get("notes")).strip() or None if p.get("notes") else None
    if "screenshot_url" in p:
        u = str(p.get("screenshot_url") or "").strip()
        e.screenshot_url = u[:500] if u.startswith("http") else None
    for field in ("entry_price", "exit_price", "size", "r_result", "pnl"):
        if field in p:
            setattr(e, field, _num(p.get(field)))
    if "traded_at" in p:
        e.traded_at = _parse_dt(p.get("traded_at"))


@router.get("")
async def list_entries(user: User = Depends(current_user),
                       session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(
        select(JournalEntry)
        .where(JournalEntry.user_id == user.id)
        .order_by(JournalEntry.traded_at.desc().nullslast(), JournalEntry.id.desc())
    )).scalars().all()
    return {"entries": [_out(e) for e in rows]}


@router.post("")
async def create_entry(payload: dict, user: User = Depends(current_user),
                       session: AsyncSession = Depends(get_session)):
    if not str(payload.get("instrument") or "").strip():
        raise HTTPException(status_code=400, detail="Instrument je povinný")
    e = JournalEntry(user_id=user.id, instrument="?", direction="long")
    _apply(e, payload)
    session.add(e)
    await session.commit()
    await session.refresh(e)
    return {"entry": _out(e)}


async def _owned(entry_id: int, user: User, session: AsyncSession) -> JournalEntry:
    e = await session.get(JournalEntry, entry_id)
    if e is None or e.user_id != user.id:
        raise HTTPException(status_code=404, detail="Záznam nenalezen")
    return e


@router.patch("/{entry_id}")
async def update_entry(entry_id: int, payload: dict, user: User = Depends(current_user),
                       session: AsyncSession = Depends(get_session)):
    e = await _owned(entry_id, user, session)
    _apply(e, payload)
    await session.commit()
    await session.refresh(e)
    return {"entry": _out(e)}


@router.delete("/{entry_id}")
async def delete_entry(entry_id: int, user: User = Depends(current_user),
                       session: AsyncSession = Depends(get_session)):
    e = await _owned(entry_id, user, session)
    await session.delete(e)
    await session.commit()
    return {"status": "ok"}


def _outcome(e: JournalEntry) -> str | None:
    """win / loss / be z r_result (priorita) nebo pnl; None = neznámé (chybí obojí)."""
    v = e.r_result if e.r_result is not None else e.pnl
    if v is None:
        return None
    return "win" if v > 0 else ("loss" if v < 0 else "be")


def _bucket_stats(entries: list[JournalEntry], key) -> list[dict]:
    groups: dict[str, list[JournalEntry]] = {}
    for e in entries:
        k = key(e)
        if k:
            groups.setdefault(k, []).append(e)
    out = []
    for k, items in groups.items():
        outc = [_outcome(e) for e in items]
        decided = [o for o in outc if o is not None]
        wins = sum(1 for o in decided if o == "win")
        rs = [e.r_result for e in items if e.r_result is not None]
        out.append({
            "key": k,
            "n": len(items),
            "win_rate": round(100 * wins / len(decided), 0) if decided else None,
            "avg_r": round(sum(rs) / len(rs), 2) if rs else None,
        })
    out.sort(key=lambda x: x["n"], reverse=True)
    return out


@router.get("/stats")
async def journal_stats(user: User = Depends(current_user),
                        session: AsyncSession = Depends(get_session)):
    entries = (await session.execute(
        select(JournalEntry).where(JournalEntry.user_id == user.id)
    )).scalars().all()

    total = len(entries)
    outc = [_outcome(e) for e in entries]
    decided = [o for o in outc if o is not None]
    wins = sum(1 for o in decided if o == "win")
    losses = sum(1 for o in decided if o == "loss")
    be = sum(1 for o in decided if o == "be")
    rs = [e.r_result for e in entries if e.r_result is not None]
    pnls = [e.pnl for e in entries if e.pnl is not None]

    return {
        "totals": {
            "trades": total,
            "decided": len(decided),
            "wins": wins,
            "losses": losses,
            "breakeven": be,
            "win_rate": round(100 * wins / len(decided), 0) if decided else None,
            "avg_r": round(sum(rs) / len(rs), 2) if rs else None,       # ~expektance v R
            "sum_r": round(sum(rs), 2) if rs else None,
            "best_r": round(max(rs), 2) if rs else None,
            "worst_r": round(min(rs), 2) if rs else None,
            "sum_pnl": round(sum(pnls), 2) if pnls else None,
        },
        "by_setup": _bucket_stats(entries, lambda e: e.setup),
        "by_session": _bucket_stats(entries, lambda e: e.session),
        "by_instrument": _bucket_stats(entries, lambda e: e.instrument),
    }
