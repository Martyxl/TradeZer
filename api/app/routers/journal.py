"""Obchodní deník — CRUD záznamů + souhrnná statistika. Vše per-user (Bearer token).

MVP: ruční zápis. Vlastnictví se hlídá přes user_id z tokenu (current_user);
uživatel nikdy nevidí ani nemění cizí záznamy.
"""
from __future__ import annotations

import base64
import json
import re
from datetime import datetime

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.llm.client import llm_client
from app.models import User
from app.models.journal import JournalEntry, JournalAnalysisJob
from app.routers.admin import _verify_token
from app.routers.auth import current_user

log = structlog.get_logger(__name__)

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
        if d in ("buy", "long", "l"):
            e.direction = "long"
        elif d in ("sell", "short", "s"):
            e.direction = "short"
        else:
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


@router.post("/import")
async def import_entries(payload: dict, user: User = Depends(current_user),
                        session: AsyncSession = Depends(get_session)):
    """Hromadný import obchodů (frontend rozparsuje CSV a namapuje sloupce na pole).
    Tělo: {rows: [{instrument, direction, entry_price, exit_price, size, r_result,
    pnl, traded_at, session, setup, notes}, ...]}. Vrací počet vytvořených + chyby."""
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise HTTPException(status_code=400, detail="Chybí rows (pole obchodů).")
    if len(rows) > 2000:
        raise HTTPException(status_code=400, detail="Max 2000 řádků na import.")
    created = 0
    errors: list[dict] = []
    for i, r in enumerate(rows):
        if not isinstance(r, dict) or not str(r.get("instrument") or "").strip():
            errors.append({"row": i + 1, "error": "chybí instrument"})
            continue
        try:
            e = JournalEntry(user_id=user.id, instrument="?", direction="long")
            _apply(e, r)
            session.add(e)
            created += 1
        except Exception as ex:  # noqa: BLE001
            errors.append({"row": i + 1, "error": str(ex)[:120]})
    if created:
        await session.commit()
    return {"created": created, "error_count": len(errors), "errors": errors[:25]}


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


# ---------------------------------------------------------------- AI vision analýza (TradingView)

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124 Safari/537.36")
_IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif")
_MAX_IMG = 8 * 1024 * 1024


async def _resolve_tv_image(url: str) -> tuple[bytes, str]:
    """Z TradingView (nebo přímého) odkazu vrať (bytes, media_type). Snapshot link
    /x/ID/ → z og:image stáhne PNG. HTTPException s návodem při selhání."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Neplatná URL")
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20.0,
                                     headers={"User-Agent": _UA}) as cl:
            img_url = url
            if not url.lower().split("?")[0].endswith(_IMG_EXT):
                r = await cl.get(url)
                r.raise_for_status()
                m = (re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', r.text, re.I)
                     or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', r.text, re.I))
                if not m:
                    raise HTTPException(status_code=400, detail=(
                        "Z odkazu nešel získat obrázek grafu. Použij TradingView snapshot "
                        "(ikona fotoaparátu → Copy link to the chart image) nebo nahraj obrázek."))
                img_url = m.group(1)
            ir = await cl.get(img_url)
            ir.raise_for_status()
            data = ir.content
            if len(data) > _MAX_IMG:
                raise HTTPException(status_code=400, detail="Obrázek je moc velký (max 8 MB).")
            ctype = ir.headers.get("content-type", "").split(";")[0].strip().lower()
            return data, ctype if ctype.startswith("image/") else "image/png"
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.warning("TV image resolve failed", url=url, error=str(e))
        raise HTTPException(status_code=400, detail=(
            "Odkaz se nepodařilo načíst. Zkontroluj, že je veřejný (TradingView snapshot), "
            "nebo nahraj obrázek."))


def _derive_direction(data: dict) -> str:
    """Směr určuj z GEOMETRIE úrovní (spolehlivější než vizuální odhad modelu):
    short = stop nad entry / target pod entry; long = opačně. Fallback na model."""
    e, s, t = _num(data.get("entry")), _num(data.get("stop")), _num(data.get("target"))
    if e is not None and s is not None and s != e:
        return "short" if s > e else "long"
    if e is not None and t is not None and t != e:
        return "long" if t > e else "short"
    d = str(data.get("direction") or "").lower().strip()
    return d if d in DIRECTIONS else ""


def _map_extracted(data: dict, source_url: str | None) -> dict:
    """Vytěžená vision pole → tvar formuláře deníku (řetězce/čísla)."""
    direction = _derive_direction(data)
    tf = str(data.get("timeframe") or "").strip()
    setup = str(data.get("setup") or "").strip()
    if tf and setup:
        setup = f"{setup} ({tf})"
    elif tf:
        setup = tf
    notes = str(data.get("notes") or "").strip()
    stop = data.get("stop")
    if stop is not None and _num(stop) is not None:
        notes = (notes + f" | Stop: {stop}").strip(" |")
    return {
        "instrument": str(data.get("instrument") or "").strip(),
        "direction": direction,
        "entry_price": data.get("entry"),
        "exit_price": data.get("target"),
        "r_result": data.get("rr"),
        "setup": setup[:80],
        "notes": notes,
        "screenshot_url": source_url or "",
    }


@router.post("/analyze")
async def analyze(payload: dict, user: User = Depends(current_user),
                  session: AsyncSession = Depends(get_session)):
    """AI extrakce obchodu z TradingView. engine=claude (synchronně → extracted hned)
    nebo engine=spark (async job → worker na Sparku → poll GET /analyze/{id})."""
    engine = (payload.get("engine") or "claude").lower()
    if engine not in ("claude", "spark"):
        engine = "claude"
    tv_url = (payload.get("tradingview_url") or "").strip()
    image_b64 = payload.get("image_base64") or ""

    if engine == "spark":
        if not tv_url:
            raise HTTPException(status_code=400, detail=(
                "Spark engine potřebuje TradingView odkaz (obrázek se neukládá)."))
        job = JournalAnalysisJob(user_id=user.id, engine="spark", source_url=tv_url, status="pending")
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return {"status": "pending", "job_id": job.id}

    # claude — synchronně v request handleru
    if image_b64:
        try:
            raw = base64.b64decode(image_b64.split(",")[-1])
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="Neplatný obrázek.")
        media = image_b64[5:].split(";")[0] if image_b64.startswith("data:") else "image/png"
        media = media or "image/png"
    elif tv_url:
        raw, media = await _resolve_tv_image(tv_url)
    else:
        raise HTTPException(status_code=400, detail="Zadej TradingView odkaz nebo obrázek.")

    extracted, meta = llm_client.extract_trade_from_image(raw, media)
    if not extracted:
        raise HTTPException(status_code=502, detail=(
            "Vision analýza se nepodařila. Zkus to znovu nebo zadej obchod ručně."))
    return {"status": "done", "extracted": _map_extracted(extracted, tv_url or None),
            "meta": {**(meta or {}), "engine": "claude"}}


@router.get("/analyze/pending")
async def analyze_pending(_: None = Depends(_verify_token),
                          session: AsyncSession = Depends(get_session)):
    """Worker (Spark) si vyzvedne pending spark joby."""
    rows = (await session.execute(
        select(JournalAnalysisJob)
        .where(JournalAnalysisJob.status == "pending", JournalAnalysisJob.engine == "spark")
        .order_by(JournalAnalysisJob.id).limit(20)
    )).scalars().all()
    return {"jobs": [{"id": j.id, "source_url": j.source_url} for j in rows]}


@router.post("/analyze/{job_id}/result")
async def analyze_result(job_id: int, payload: dict, _: None = Depends(_verify_token),
                         session: AsyncSession = Depends(get_session)):
    """Worker pushne výsledek vision extrakce (nebo chybu)."""
    job = await session.get(JournalAnalysisJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job nenalezen")
    err = payload.get("error")
    extracted = payload.get("extracted")
    if err or not isinstance(extracted, dict):
        job.status = "failed"
        job.error = str(err or "prázdný výsledek")[:500]
    else:
        job.status = "done"
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else None
        job.result = json.dumps(
            {"extracted": _map_extracted(extracted, job.source_url), "meta": meta},
            ensure_ascii=False)
    await session.commit()
    return {"status": "ok"}


@router.get("/analyze/{job_id}")
async def analyze_status(job_id: int, user: User = Depends(current_user),
                         session: AsyncSession = Depends(get_session)):
    """Frontend polluje stav spark jobu."""
    job = await session.get(JournalAnalysisJob, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Job nenalezen")
    out: dict = {"status": job.status, "job_id": job.id}
    if job.status == "done" and job.result:
        r = json.loads(job.result)
        if isinstance(r, dict) and "extracted" in r:
            out["extracted"] = r["extracted"]
            if r.get("meta"):
                out["meta"] = {**r["meta"], "engine": "spark"}
        else:
            out["extracted"] = r  # zpětná kompat se staršími joby (bez meta)
    elif job.status == "failed":
        out["error"] = job.error
    return out
