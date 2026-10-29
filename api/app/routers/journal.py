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
from app.models.journal import JournalEntry, JournalAnalysisJob, JournalStrategy, JournalTag
from app.routers.admin import _verify_token
from app.routers.auth import current_user

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/journal", tags=["journal"])

DIRECTIONS = {"long", "short"}
SESSIONS = {"asia", "london", "ny", "other"}
OUTCOMES = {"win", "loss", "be"}
TAG_KINDS = ("setup", "timeframe", "mistake")

# Výchozí tagy, které se založí každému uživateli při prvním otevření deníku.
DEFAULT_TAGS: dict[str, list[str]] = {
    "setup": ["FVG", "iFVG", "OB", "Fibo OTE", "Liquidity"],
    "timeframe": ["M1", "M5", "M15", "H1", "H4", "D1"],
    "mistake": [
        "Nepočkal jsem na likviditu", "Vstup před OTE (FOMO)", "Bez potvrzení (MSS)",
        "Proti HTF trendu", "Posunutý / žádný SL", "Moc velká pozice",
        "Obchod během zpráv", "Revenge trade", "Předčasný výstup",
    ],
}


def _out(e: JournalEntry) -> dict:
    return {
        "id": e.id,
        "instrument": e.instrument,
        "direction": e.direction,
        "entry_price": e.entry_price,
        "exit_price": e.exit_price,
        "stop_price": e.stop_price,
        "target_price": e.target_price,
        "outcome": e.outcome,
        "size": e.size,
        "r_result": e.r_result,
        "pnl": e.pnl,
        "traded_at": e.traded_at.isoformat() if e.traded_at else None,
        "session": e.session,
        "setup": e.setup,
        "notes": e.notes,
        "screenshot_url": e.screenshot_url,
        "strategy_id": e.strategy_id,
        "tag_ids": e.tag_ids or [],
        "mistake_ids": e.mistake_ids or [],
        "loss_reason": e.loss_reason,
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
    for field in ("entry_price", "exit_price", "stop_price", "target_price", "size", "r_result", "pnl"):
        if field in p:
            setattr(e, field, _num(p.get(field)))
    if "outcome" in p:
        o = str(p.get("outcome") or "").lower().strip()
        e.outcome = o if o in OUTCOMES else None
    if "traded_at" in p:
        e.traded_at = _parse_dt(p.get("traded_at"))
    if "loss_reason" in p:
        e.loss_reason = (str(p.get("loss_reason") or "").strip()[:2000] or None)
    _fill_result(e)


def _id_list(v) -> list[int]:
    out: list[int] = []
    for x in v if isinstance(v, list) else []:
        try:
            i = int(x)
        except (ValueError, TypeError):
            continue
        if i not in out:
            out.append(i)
    return out[:30]


async def _apply_context(e: JournalEntry, p: dict, user: User, session: AsyncSession) -> None:
    """Strategie/tagy/chyby — jen vlastní (cizí id tiše zahodí) a správného druhu."""
    if not any(k in p for k in ("strategy_id", "tag_ids", "mistake_ids")):
        return
    kinds = dict((await session.execute(
        select(JournalTag.id, JournalTag.kind).where(JournalTag.user_id == user.id))).all())
    if "tag_ids" in p:
        e.tag_ids = [i for i in _id_list(p.get("tag_ids")) if kinds.get(i) in ("setup", "timeframe")] or None
    if "mistake_ids" in p:
        e.mistake_ids = [i for i in _id_list(p.get("mistake_ids")) if kinds.get(i) == "mistake"] or None
    if "strategy_id" in p:
        sid = _id_list([p.get("strategy_id")])
        st = await session.get(JournalStrategy, sid[0]) if sid else None
        e.strategy_id = st.id if st is not None and st.user_id == user.id else None


def _fill_result(e: JournalEntry) -> None:
    """Při známém výsledku (win/loss) dopočítá prázdné exit/R ze SL/TP/entry:
    win → exit = TP, R = |TP−entry| / |entry−SL|; loss → exit = SL, R = −1.
    Nikdy nepřepisuje hodnotu, kterou uživatel vyplnil sám."""
    if e.outcome == "loss":
        if e.exit_price is None and e.stop_price is not None:
            e.exit_price = e.stop_price
        if e.r_result is None and e.stop_price is not None:
            e.r_result = -1.0
    elif e.outcome == "win":
        if e.exit_price is None and e.target_price is not None:
            e.exit_price = e.target_price
        if (e.r_result is None and None not in (e.entry_price, e.stop_price, e.target_price)
                and e.entry_price != e.stop_price):
            e.r_result = round(abs(e.target_price - e.entry_price)
                               / abs(e.entry_price - e.stop_price), 2)


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
    await _apply_context(e, payload, user, session)
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
    await _apply_context(e, payload, user, session)
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
    """win / loss / be: explicitní `outcome` (priorita), jinak z r_result, jinak z pnl;
    None = neznámé."""
    if e.outcome in OUTCOMES:
        return e.outcome
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

    tags = {t.id: t for t in (await session.execute(
        select(JournalTag).where(JournalTag.user_id == user.id))).scalars().all()}
    strategies = {st.id: st.name for st in (await session.execute(
        select(JournalStrategy).where(JournalStrategy.user_id == user.id))).scalars().all()}

    def tag_names(e: JournalEntry, kind: str) -> list[str]:
        ids = e.mistake_ids if kind == "mistake" else e.tag_ids
        return [tags[i].name for i in ids or [] if i in tags and tags[i].kind == kind]

    def combo(e: JournalEntry) -> str | None:
        # Podmínky obchodu = setup tagy + timeframe — „za jakých podmínek se mi daří“
        parts = sorted(tag_names(e, "setup")) + sorted(tag_names(e, "timeframe"))
        return " + ".join(parts) if len(parts) >= 2 else None

    by_combo = [b for b in _bucket_stats(entries, combo) if b["n"] >= 2]
    by_combo.sort(key=lambda b: (b["avg_r"] if b["avg_r"] is not None else -99, b["n"]), reverse=True)

    # Chyby: kolikrát se objevily a kolik R stály (záporné R obchodů, u kterých je chyba zapsaná)
    mistakes: dict[str, dict] = {}
    for e in entries:
        for name in tag_names(e, "mistake"):
            m = mistakes.setdefault(name, {"key": name, "n": 0, "r_lost": 0.0})
            m["n"] += 1
            if e.r_result is not None and e.r_result < 0:
                m["r_lost"] += e.r_result
    by_mistake = sorted(({**m, "r_lost": round(m["r_lost"], 2)} for m in mistakes.values()),
                        key=lambda m: (m["n"], -m["r_lost"]), reverse=True)
    losses_list = [e for e in entries if _outcome(e) == "loss"]
    explained = sum(1 for e in losses_list if e.mistake_ids or e.loss_reason)

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
        "by_strategy": _bucket_stats(entries, lambda e: strategies.get(e.strategy_id)),
        "by_tag": _multi_bucket(entries, lambda e: tag_names(e, "setup")),
        "by_timeframe": _multi_bucket(entries, lambda e: tag_names(e, "timeframe")),
        "by_combo": by_combo[:15],
        "by_mistake": by_mistake,
        "losses": {"total": len(losses_list), "explained": explained},
    }


def _multi_bucket(entries: list[JournalEntry], keys) -> list[dict]:
    """Jako _bucket_stats, ale obchod s více tagy se započte do každého svého tagu."""
    by: dict[str, list[JournalEntry]] = {}
    for e in entries:
        for k in keys(e):
            by.setdefault(k, []).append(e)
    out = [{**_bucket_stats(items, lambda _e: "x")[0], "key": k} for k, items in by.items()]
    out.sort(key=lambda x: x["n"], reverse=True)
    return out


# ---------------------------------------------------------------- tagy a strategie

async def _ensure_default_tags(user: User, session: AsyncSession) -> None:
    has = await session.scalar(select(JournalTag.id).where(JournalTag.user_id == user.id).limit(1))
    if has is not None:
        return
    for kind, names in DEFAULT_TAGS.items():
        for i, name in enumerate(names):
            session.add(JournalTag(user_id=user.id, kind=kind, name=name, sort_order=i))
    await session.commit()


def _tag_out(t: JournalTag) -> dict:
    return {"id": t.id, "kind": t.kind, "name": t.name}


def _strategy_out(st: JournalStrategy) -> dict:
    return {"id": st.id, "name": st.name, "description": st.description, "tag_ids": st.tag_ids or []}


@router.get("/tags")
async def list_tags(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    """Tagy (setup / timeframe / mistake) a strategie uživatele. Při prvním volání založí výchozí sadu."""
    await _ensure_default_tags(user, session)
    tags = (await session.execute(select(JournalTag).where(JournalTag.user_id == user.id)
                                  .order_by(JournalTag.kind, JournalTag.sort_order, JournalTag.id))).scalars().all()
    strategies = (await session.execute(select(JournalStrategy).where(JournalStrategy.user_id == user.id)
                                        .order_by(JournalStrategy.name))).scalars().all()
    return {"tags": [_tag_out(t) for t in tags], "strategies": [_strategy_out(x) for x in strategies]}


def _clean_name(v, max_len: int, what: str) -> str:
    name = re.sub(r"\s+", " ", str(v or "")).strip()[:max_len]
    if not name:
        raise HTTPException(status_code=422, detail=f"Zadej název {what}.")
    return name


async def _owned_tag(tag_id: int, user: User, session: AsyncSession) -> JournalTag:
    t = await session.get(JournalTag, tag_id)
    if t is None or t.user_id != user.id:
        raise HTTPException(status_code=404, detail="Tag nenalezen")
    return t


async def _check_tag_unique(user: User, kind: str, name: str, session: AsyncSession,
                            skip_id: int | None = None) -> int:
    rows = (await session.execute(select(JournalTag).where(
        JournalTag.user_id == user.id, JournalTag.kind == kind))).scalars().all()
    if any(t.name.lower() == name.lower() and t.id != skip_id for t in rows):
        raise HTTPException(status_code=409, detail=f"Tag „{name}“ už máš.")
    return len(rows)


@router.post("/tags")
async def create_tag(payload: dict, user: User = Depends(current_user),
                     session: AsyncSession = Depends(get_session)):
    kind = str(payload.get("kind") or "setup")
    if kind not in TAG_KINDS:
        raise HTTPException(status_code=422, detail="Neznámý druh tagu.")
    name = _clean_name(payload.get("name"), 40, "tagu")
    n = await _check_tag_unique(user, kind, name, session)
    if n >= 60:
        raise HTTPException(status_code=422, detail="Max 60 tagů jednoho druhu.")
    t = JournalTag(user_id=user.id, kind=kind, name=name, sort_order=n)
    session.add(t)
    await session.commit()
    await session.refresh(t)
    return {"tag": _tag_out(t)}


@router.patch("/tags/{tag_id}")
async def rename_tag(tag_id: int, payload: dict, user: User = Depends(current_user),
                     session: AsyncSession = Depends(get_session)):
    t = await _owned_tag(tag_id, user, session)
    name = _clean_name(payload.get("name"), 40, "tagu")
    await _check_tag_unique(user, t.kind, name, session, skip_id=t.id)
    t.name = name
    await session.commit()
    return {"tag": _tag_out(t)}


@router.delete("/tags/{tag_id}")
async def delete_tag(tag_id: int, user: User = Depends(current_user),
                     session: AsyncSession = Depends(get_session)):
    """Smaže tag a odebere ho ze všech obchodů a strategií uživatele (obchody samotné zůstanou)."""
    t = await _owned_tag(tag_id, user, session)
    for e in (await session.execute(select(JournalEntry).where(JournalEntry.user_id == user.id))).scalars():
        if tag_id in (e.tag_ids or []):
            e.tag_ids = [i for i in e.tag_ids if i != tag_id] or None
        if tag_id in (e.mistake_ids or []):
            e.mistake_ids = [i for i in e.mistake_ids if i != tag_id] or None
    for st in (await session.execute(select(JournalStrategy).where(JournalStrategy.user_id == user.id))).scalars():
        if tag_id in (st.tag_ids or []):
            st.tag_ids = [i for i in st.tag_ids if i != tag_id] or None
    await session.delete(t)
    await session.commit()
    return {"status": "ok"}


async def _apply_strategy(st: JournalStrategy, p: dict, user: User, session: AsyncSession) -> None:
    if "name" in p:
        st.name = _clean_name(p.get("name"), 60, "strategie")
    if "description" in p:
        st.description = str(p.get("description") or "").strip()[:2000] or None
    if "tag_ids" in p:
        own = set((await session.execute(select(JournalTag.id).where(
            JournalTag.user_id == user.id, JournalTag.kind.in_(("setup", "timeframe"))))).scalars())
        st.tag_ids = [i for i in _id_list(p.get("tag_ids")) if i in own] or None


@router.post("/strategies")
async def create_strategy(payload: dict, user: User = Depends(current_user),
                          session: AsyncSession = Depends(get_session)):
    st = JournalStrategy(user_id=user.id, name="?")
    await _apply_strategy(st, {"name": payload.get("name"), **payload}, user, session)
    session.add(st)
    await session.commit()
    await session.refresh(st)
    return {"strategy": _strategy_out(st)}


async def _owned_strategy(sid: int, user: User, session: AsyncSession) -> JournalStrategy:
    st = await session.get(JournalStrategy, sid)
    if st is None or st.user_id != user.id:
        raise HTTPException(status_code=404, detail="Strategie nenalezena")
    return st


@router.patch("/strategies/{sid}")
async def update_strategy(sid: int, payload: dict, user: User = Depends(current_user),
                          session: AsyncSession = Depends(get_session)):
    st = await _owned_strategy(sid, user, session)
    await _apply_strategy(st, payload, user, session)
    await session.commit()
    return {"strategy": _strategy_out(st)}


@router.delete("/strategies/{sid}")
async def delete_strategy(sid: int, user: User = Depends(current_user),
                          session: AsyncSession = Depends(get_session)):
    """Smaže strategii; obchody zůstanou (bez strategie, jejich tagy se nemění)."""
    st = await _owned_strategy(sid, user, session)
    for e in (await session.execute(select(JournalEntry).where(
            JournalEntry.user_id == user.id, JournalEntry.strategy_id == sid))).scalars():
        e.strategy_id = None
    await session.delete(st)
    await session.commit()
    return {"status": "ok"}


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
    stop, target, rr = _num(data.get("stop")), _num(data.get("target")), _num(data.get("rr"))
    # Výsledek obchodu: plánované RR NENÍ výsledek. exit/R se vyplní jen když je znám
    # (win = TP + plánované RR, loss = SL + −1R); "open"/neznámé → prázdné, ať to nevypadá jako výhra.
    outcome = str(data.get("outcome") or "").lower().strip()
    exit_price = r_result = None
    if outcome == "win":
        exit_price, r_result = target, rr
    elif outcome == "loss":
        exit_price, r_result = stop, -1.0
    def fmt(x: float) -> str:  # bez ořezu platných číslic (:g by z 31167.22 udělalo 31167.2)
        return f"{x:.4f}".rstrip("0").rstrip(".")
    levels = []
    if stop is not None:
        levels.append(f"SL: {fmt(stop)}")
    if target is not None:
        levels.append(f"TP: {fmt(target)}")
    if rr is not None:
        levels.append(f"plán RR {fmt(rr)}")
    levels.append({"win": "výsledek: WIN (cena dosáhla TP)",
                   "loss": "výsledek: LOSS (cena dosáhla SL)"}.get(
                       outcome, "výsledek: neurčen/běží — doplň ručně"))
    notes = " | ".join(x for x in (str(data.get("notes") or "").strip(), *levels) if x)
    return {
        "instrument": str(data.get("instrument") or "").strip(),
        "direction": direction,
        "entry_price": data.get("entry"),
        "exit_price": exit_price,
        "stop_price": stop,
        "target_price": target,
        "outcome": outcome if outcome in ("win", "loss") else "",
        "r_result": r_result,
        "traded_at": data.get("traded_at") or "",
        "setup": setup[:80],
        "notes": notes,
        "screenshot_url": source_url or "",
    }


@router.post("/analyze")
async def analyze(payload: dict, user: User = Depends(current_user),
                  session: AsyncSession = Depends(get_session)):
    """AI extrakce obchodu z TradingView. engine=claude (synchronně → extracted hned)
    nebo engine=spark (async job → worker na Sparku → poll GET /analyze/{id}).
    ZATÍM JEN PRO ADMINY (ostatním frontend ukazuje „Coming soon“) — vynuceno i tady, ať to nejde
    obejít přímým voláním API."""
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="AI čtení grafu z TradingView připravujeme (coming soon).")
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
