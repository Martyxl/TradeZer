"""Investorský deník — portfolio transakce + dashboard se živými cenami.

Per-user (current_user z tokenu). Holdings se počítají z transakcí metodou
průměrné ceny; živá hodnota z InvestmentQuote (push z rezidenční IP). Import
z brokerů normalizuje řádky do transakcí (parser detekuje broker ve frontendu
nebo v broker_import službě). Dedup přes dedup_hash.
"""
from __future__ import annotations

import hashlib
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import User, InvestmentTx, InvestmentQuote
from app.routers.admin import _verify_token
from app.routers.auth import current_user

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/investments", tags=["investments"])

TX_TYPES = ("buy", "sell", "dividend", "fee", "deposit", "withdrawal")
DEFAULT_BASE = "CZK"


def _num(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(" ", "").replace(",", "."))
    except (ValueError, TypeError):
        return None


def _parse_dt(v) -> datetime | None:
    if not v:
        return None
    if isinstance(v, datetime):
        return v
    s = str(v).strip().replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d.%m.%Y %H:%M:%S",
                "%d.%m.%Y", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s[:len(fmt) + 4], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _out(t: InvestmentTx) -> dict:
    return {
        "id": t.id, "broker": t.broker, "tx_type": t.tx_type, "symbol": t.symbol,
        "name": t.name, "quantity": t.quantity, "price": t.price, "currency": t.currency,
        "fee": t.fee, "amount": t.amount,
        "executed_at": t.executed_at.isoformat() if t.executed_at else None,
        "notes": t.notes, "source": t.source,
    }


def _hash(user_id: int, p: dict) -> str:
    key = f"{user_id}|{p.get('broker')}|{p.get('tx_type')}|{p.get('symbol')}|{p.get('quantity')}|{p.get('price')}|{p.get('executed_at')}|{p.get('amount')}"
    return hashlib.sha256(key.encode()).hexdigest()[:40]


def _apply(t: InvestmentTx, p: dict) -> None:
    if "broker" in p and p["broker"]:
        t.broker = str(p["broker"]).strip().lower()[:20]
    if "tx_type" in p and p["tx_type"]:
        tt = str(p["tx_type"]).strip().lower()
        t.tx_type = tt if tt in TX_TYPES else "buy"
    if "symbol" in p:
        t.symbol = (str(p["symbol"]).strip().upper()[:40] or None) if p["symbol"] else None
    if "name" in p:
        t.name = (str(p["name"]).strip()[:120] or None) if p["name"] else None
    if "currency" in p and p["currency"]:
        t.currency = str(p["currency"]).strip().upper()[:8]
    for f in ("quantity", "price", "fee", "amount"):
        if f in p:
            setattr(t, f, _num(p[f]))
    if "executed_at" in p:
        t.executed_at = _parse_dt(p["executed_at"])
    if "notes" in p:
        t.notes = (str(p["notes"]).strip() or None) if p["notes"] else None


# ── CRUD ────────────────────────────────────────────────────────────────────
@router.get("")
async def list_tx(user: User = Depends(current_user),
                  session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(
        select(InvestmentTx).where(InvestmentTx.user_id == user.id)
        .order_by(InvestmentTx.executed_at.desc().nullslast(), InvestmentTx.id.desc())
    )).scalars().all()
    return {"transactions": [_out(t) for t in rows]}


@router.post("")
async def create_tx(payload: dict, user: User = Depends(current_user),
                    session: AsyncSession = Depends(get_session)):
    t = InvestmentTx(user_id=user.id, tx_type="buy", currency="USD")
    _apply(t, payload)
    if t.tx_type in ("buy", "sell") and not t.symbol:
        raise HTTPException(status_code=400, detail="Nákup/prodej vyžaduje ticker.")
    t.dedup_hash = _hash(user.id, _out(t))
    session.add(t)
    await session.commit()
    return _out(t)


@router.post("/import")
async def import_tx(payload: dict, user: User = Depends(current_user),
                    session: AsyncSession = Depends(get_session)):
    """Hromadný import transakcí (frontend/broker_import rozparsuje CSV → rows).
    Dedup přes dedup_hash — opakovaný import stejného souboru nepřidá duplicity."""
    rows = payload.get("rows") or []
    if not isinstance(rows, list):
        raise HTTPException(status_code=400, detail="rows musí být seznam.")
    if len(rows) > 5000:
        raise HTTPException(status_code=400, detail="Max 5000 řádků na import.")
    source = (payload.get("source") or "import")[:60]
    broker = (payload.get("broker") or "").strip().lower()[:20]

    existing = set((await session.execute(
        select(InvestmentTx.dedup_hash).where(InvestmentTx.user_id == user.id)
    )).scalars().all())

    created, skipped, errors = 0, 0, []
    for i, row in enumerate(rows):
        try:
            t = InvestmentTx(user_id=user.id, tx_type="buy", currency="USD", source=source)
            if broker:
                t.broker = broker
            _apply(t, row)
            if t.tx_type in ("buy", "sell") and not t.symbol:
                errors.append(f"řádek {i + 1}: chybí ticker")
                continue
            h = _hash(user.id, _out(t) | {"amount": t.amount})
            if h in existing:
                skipped += 1
                continue
            t.dedup_hash = h
            existing.add(h)
            session.add(t)
            created += 1
        except Exception as e:  # noqa: BLE001
            errors.append(f"řádek {i + 1}: {e}")
    await session.commit()
    return {"created": created, "skipped": skipped, "errors": errors[:20]}


async def _owned(tx_id: int, user: User, session: AsyncSession) -> InvestmentTx:
    t = await session.get(InvestmentTx, tx_id)
    if not t or t.user_id != user.id:
        raise HTTPException(status_code=404, detail="Nenalezeno")
    return t


@router.patch("/{tx_id}")
async def update_tx(tx_id: int, payload: dict, user: User = Depends(current_user),
                    session: AsyncSession = Depends(get_session)):
    t = await _owned(tx_id, user, session)
    _apply(t, payload)
    t.dedup_hash = _hash(user.id, _out(t) | {"amount": t.amount})
    await session.commit()
    return _out(t)


@router.delete("/{tx_id}")
async def delete_tx(tx_id: int, user: User = Depends(current_user),
                    session: AsyncSession = Depends(get_session)):
    t = await _owned(tx_id, user, session)
    await session.delete(t)
    await session.commit()
    return {"status": "deleted"}


# ── Portfolio (holdings + živá hodnota) ─────────────────────────────────────
def _to_base(amount: float | None, ccy: str, base: str, fx: dict[str, float]) -> float | None:
    if amount is None:
        return None
    if ccy == base:
        return amount
    rate = fx.get(f"{ccy}{base}")
    if rate:
        return amount * rate
    inv = fx.get(f"{base}{ccy}")
    if inv:
        return amount / inv
    return None


@router.get("/portfolio")
async def portfolio(base: str = Query(DEFAULT_BASE), user: User = Depends(current_user),
                    session: AsyncSession = Depends(get_session)):
    base = base.strip().upper()[:8]
    txs = (await session.execute(
        select(InvestmentTx).where(InvestmentTx.user_id == user.id)
        .order_by(InvestmentTx.executed_at.asc().nullsfirst(), InvestmentTx.id.asc())
    )).scalars().all()

    # Live ceny + FX
    quotes = {q.symbol: q for q in (await session.execute(select(InvestmentQuote))).scalars().all()}
    fx = {s: q.price for s, q in quotes.items() if len(s) == 6 and s.isalpha()}

    # Agregace metodou průměrné ceny (per symbol).
    H: dict[str, dict] = {}
    realized_by_ccy: dict[str, float] = {}
    dividends_by_ccy: dict[str, float] = {}
    for t in txs:
        ccy = t.currency or "USD"
        if t.tx_type == "dividend":
            dividends_by_ccy[ccy] = dividends_by_ccy.get(ccy, 0) + (t.amount or 0)
            continue
        if t.tx_type not in ("buy", "sell") or not t.symbol:
            continue
        h = H.setdefault(t.symbol, {"qty": 0.0, "cost": 0.0, "currency": ccy, "name": t.name})
        if t.name and not h["name"]:
            h["name"] = t.name
        q = t.quantity or 0
        price = t.price or 0
        fee = t.fee or 0
        if t.tx_type == "buy":
            h["qty"] += q
            h["cost"] += q * price + fee
        else:  # sell
            avg = (h["cost"] / h["qty"]) if h["qty"] else 0
            realized_by_ccy[ccy] = realized_by_ccy.get(ccy, 0) + (price - avg) * q - fee
            h["cost"] -= avg * q
            h["qty"] -= q

    holdings = []
    totals_ccy: dict[str, dict] = {}
    base_value = base_invested = 0.0
    base_complete = True
    for sym, h in sorted(H.items()):
        if h["qty"] <= 1e-9:
            continue
        ccy = h["currency"]
        avg_cost = h["cost"] / h["qty"]
        invested = h["cost"]
        q = quotes.get(sym)
        cur_price = q.price if q else None
        cur_value = h["qty"] * cur_price if cur_price is not None else None
        unreal = (cur_value - invested) if cur_value is not None else None
        unreal_pct = (unreal / invested * 100) if (unreal is not None and invested) else None
        holdings.append({
            "symbol": sym, "name": h["name"], "quantity": round(h["qty"], 6),
            "avg_cost": round(avg_cost, 4), "invested": round(invested, 2), "currency": ccy,
            "price": cur_price, "value": round(cur_value, 2) if cur_value is not None else None,
            "unrealized": round(unreal, 2) if unreal is not None else None,
            "unrealized_pct": round(unreal_pct, 2) if unreal_pct is not None else None,
            "price_as_of": q.as_of.isoformat() if (q and q.as_of) else None,
        })
        tc = totals_ccy.setdefault(ccy, {"invested": 0.0, "value": 0.0, "has_value": True})
        tc["invested"] += invested
        if cur_value is not None:
            tc["value"] += cur_value
        else:
            tc["has_value"] = False
        bi = _to_base(invested, ccy, base, fx)
        bv = _to_base(cur_value, ccy, base, fx) if cur_value is not None else None
        if bi is None or (cur_value is not None and bv is None):
            base_complete = False
        else:
            base_invested += bi
            base_value += bv if bv is not None else 0

    return {
        "base": base,
        "holdings": holdings,
        "by_currency": {c: {"invested": round(v["invested"], 2),
                            "value": round(v["value"], 2) if v["has_value"] else None}
                        for c, v in totals_ccy.items()},
        "realized_by_currency": {c: round(v, 2) for c, v in realized_by_ccy.items()},
        "dividends_by_currency": {c: round(v, 2) for c, v in dividends_by_ccy.items()},
        "base_totals": {
            "invested": round(base_invested, 2),
            "value": round(base_value, 2),
            "unrealized": round(base_value - base_invested, 2),
            "complete": base_complete,  # False = chybí nějaký FX/quote
        },
        "fx_available": sorted(fx.keys()),
    }


# ── Živé ceny (push z rezidenční IP) ────────────────────────────────────────
@router.get("/symbols", dependencies=[Depends(_verify_token)])
async def held_symbols(session: AsyncSession = Depends(get_session)):
    """Pro quote scanner: seznam držených symbolů + měn napříč uživateli."""
    rows = (await session.execute(
        select(InvestmentTx.symbol, InvestmentTx.currency)
        .where(InvestmentTx.symbol.isnot(None),
               InvestmentTx.tx_type.in_(("buy", "sell"))).distinct()
    )).all()
    syms = sorted({r.symbol for r in rows if r.symbol})
    ccys = sorted({r.currency for r in rows if r.currency})
    return {"symbols": syms, "currencies": ccys}


@router.post("/admin-import", dependencies=[Depends(_verify_token)])
async def admin_import(payload: dict, session: AsyncSession = Depends(get_session)):
    """DOČASNÉ: import transakcí do účtu podle emailu/username (interní token).
    Pro jednorázové nahrání brokerských výpisů, když nemáme Bearer uživatele."""
    account = (payload.get("account") or "").strip()
    rows = payload.get("rows") or []
    user = await session.scalar(
        select(User).where((User.email == account) | (User.username == account))
    )
    if user is None:
        cands = (await session.execute(
            select(User.id, User.email, User.username).where(
                User.email.ilike("%mart%") | User.username.ilike("%mart%"))
        )).all()
        return {"error": "user_not_found", "candidates": [{"id": c.id, "email": c.email, "username": c.username} for c in cands]}

    if payload.get("replace"):
        await session.execute(delete(InvestmentTx).where(
            InvestmentTx.user_id == user.id, InvestmentTx.broker.in_(["xtb", "etoro"])))
        await session.commit()

    existing = set((await session.execute(
        select(InvestmentTx.dedup_hash).where(InvestmentTx.user_id == user.id)
    )).scalars().all())
    created, skipped = 0, 0
    for row in rows:
        t = InvestmentTx(user_id=user.id, tx_type="buy", currency="USD", source=row.get("source") or "broker-import")
        _apply(t, row)
        if t.tx_type in ("buy", "sell") and not t.symbol:
            continue
        # Dedup dle brokerského ref (ID pozice/operace) — stabilní přes re-import,
        # nekoliduje u legitimně stejných per-lot dividend/frakčních nákupů.
        ref = row.get("ref")
        h = hashlib.sha256(f"{user.id}|{ref}".encode()).hexdigest()[:40] if ref else _hash(user.id, _out(t) | {"amount": t.amount})
        if h in existing:
            skipped += 1
            continue
        t.dedup_hash = h
        existing.add(h)
        session.add(t)
        created += 1
    await session.commit()
    return {"status": "ok", "user_id": user.id, "created": created, "skipped": skipped}


@router.post("/quotes/ingest", dependencies=[Depends(_verify_token)])
async def ingest_quotes(payload: dict, session: AsyncSession = Depends(get_session)):
    """Upsert živých cen/FX. payload = {"quotes": [{symbol, price, currency?, as_of?}]}."""
    items = payload.get("quotes") or []
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="quotes musí být seznam.")
    n = 0
    for it in items:
        sym = (it.get("symbol") or "").strip().upper()[:40]
        price = _num(it.get("price"))
        if not sym or price is None:
            continue
        q = await session.get(InvestmentQuote, sym)
        if q is None:
            q = InvestmentQuote(symbol=sym, price=price)
            session.add(q)
        q.price = price
        if it.get("currency"):
            q.currency = str(it["currency"]).strip().upper()[:8]
        q.as_of = _parse_dt(it.get("as_of")) or datetime.utcnow()
        q.source = (it.get("source") or "yahoo")[:40]
        n += 1
    await session.commit()
    return {"status": "ok", "updated": n}
