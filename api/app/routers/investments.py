"""Investorský deník — portfolio transakce + dashboard se živými cenami.

Per-user (current_user z tokenu). Holdings se počítají z transakcí metodou
průměrné ceny; živá hodnota z InvestmentQuote (push z rezidenční IP). Import
z brokerů normalizuje řádky do transakcí (parser detekuje broker ve frontendu
nebo v broker_import službě). Dedup přes dedup_hash.
"""
from __future__ import annotations

import bisect
import hashlib
from datetime import datetime, date as date_cls, timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import User, InvestmentTx, InvestmentQuote, InvestmentPriceDaily
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


def _signal(h: dict, weight: float | None, raw_qty: float, verdict: str | None = None) -> dict:
    """Pravidlový semafor pro pozici — transparentní, NE investiční doporučení.
    Vstupy: nerealizovaný zisk %, váha v portfoliu, poloha v 52T rozpětí a (je-li)
    verdikt Valuation Radaru. Výstup: barva (green/amber/red), důvody, návrh akce,
    zóna k dokupu."""
    reasons: list[str] = []
    score = 0  # + = spíš odebrat/trimovat, − = spíš držet/dokoupit
    up = h.get("unrealized_pct")
    price = h.get("price")
    hi, lo = h.get("high_52w"), h.get("low_52w")
    pos52 = None
    if price and hi and lo and hi > lo:
        pos52 = (price - lo) / (hi - lo)
    v = (verdict or "").upper()
    overvalued = "PŘEPÁL" in v or "PREPAL" in v
    cheap = "LEVN" in v

    if up is not None and up >= 60:
        reasons.append(f"velký zisk +{up:.0f} %"); score += 1
    if weight is not None and weight >= 15:
        reasons.append(f"velká váha v portfoliu {weight:.0f} %"); score += 1
    if overvalued:
        reasons.append("valuace je podle Valuation Radaru přepálená"); score += 1
    elif cheap:
        reasons.append("valuace je podle Valuation Radaru levná"); score -= 1
    if pos52 is not None:
        if pos52 >= 0.9:
            reasons.append("blízko 52T maxima"); score += 1
        elif pos52 <= 0.15:
            if verdict is None:
                # sama cena u minima nic neříká o kvalitě firmy (může klesat dál) → bez valuace jen slabý signál
                reasons.append("blízko 52T minima (bez ověření valuací — může jít o pokračující pokles)")
            else:
                reasons.append("blízko 52T minima"); score -= 1

    color = "red" if score >= 2 else ("green" if score <= -1 else "amber")

    action, trim_qty = "držet / sledovat", None
    if color == "red":
        if weight is not None and weight >= 15:
            trim_qty = round(raw_qty * (1 - 10.0 / weight), 4)
            action = f"zvážit odebrání ~{trim_qty} ks (snížit váhu k 10 %)"
        else:
            action = "zvážit postupné odebrání části zisku"
    elif color == "green":
        action = "prostor k případnému dokupu"

    # Zóna k dokupu: třetina cesty od 52T minima k ceně, jinak ~−10 % od ceny.
    add_zone = None
    if price:
        add_zone = round(lo + (price - lo) * 0.33, 2) if (lo and pos52 is not None) else round(price * 0.9, 2)

    return {"color": color, "reasons": reasons, "action": action,
            "trim_qty": trim_qty, "add_zone": add_zone,
            "pos_52w": round(pos52 * 100, 1) if pos52 is not None else None}


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
            "high_52w": q.high_52w if q else None, "low_52w": q.low_52w if q else None,
            "_bv": None, "_raw_qty": h["qty"],
        })
        tc = totals_ccy.setdefault(ccy, {"invested": 0.0, "value": 0.0, "has_value": True})
        tc["invested"] += invested
        if cur_value is not None:
            tc["value"] += cur_value
        else:
            tc["has_value"] = False
        bi = _to_base(invested, ccy, base, fx)
        bv = _to_base(cur_value, ccy, base, fx) if cur_value is not None else None
        holdings[-1]["_bv"] = bv
        if bi is None or (cur_value is not None and bv is None):
            base_complete = False
        else:
            base_invested += bi
            base_value += bv if bv is not None else 0

    # Verdikty Valuation Radaru (předpočtený snapshot, jedno čtení) — ticker bez broker suffixu
    verdicts: dict[str, str] = {}
    try:
        from app.valuation.models import ValOverviewSnapshot
        snap = await session.get(ValOverviewSnapshot, "latest")
        for it in ((snap.payload or {}).get("items", []) if snap else []):
            if it.get("ticker") and it.get("valuation_verdict"):
                verdicts[str(it["ticker"]).upper()] = it["valuation_verdict"]
    except Exception as e:  # noqa: BLE001 — semafor funguje i bez valuací
        log.warning("investments: valuation verdicts unavailable", error=str(e))

    # Semafor — druhý průchod (potřebuje celkovou hodnotu pro váhu pozice).
    for hd in holdings:
        weight = (hd.pop("_bv") / base_value * 100) if (base_value and hd.get("_bv")) else None
        raw_qty = hd.pop("_raw_qty")
        hd["weight_pct"] = round(weight, 2) if weight is not None else None
        hd["signal"] = _signal(hd, weight, raw_qty, verdicts.get(hd["symbol"].split(".")[0].upper()))

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


# ── Daňový časový test (ČR: >3 roky držení → osvobození od daně z příjmu) ────
TIMETEST_YEARS = 3


def _add_years(d: datetime, years: int) -> datetime:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29. února
        return d.replace(year=d.year + years, day=28)


@router.get("/timetest")
async def tax_timetest(base: str = Query(DEFAULT_BASE), user: User = Depends(current_user),
                       session: AsyncSession = Depends(get_session)):
    """Český časový test: cenný papír držený >3 roky → zisk z prodeje osvobozen
    od daně z příjmu. Pro každý zbývající nákupní lot (FIFO po odečtení prodejů)
    spočítá datum osvobození (nákup + 3 roky) a kolik zbývá. NE daňové poradenství."""
    base = base.strip().upper()[:8]
    txs = (await session.execute(
        select(InvestmentTx).where(InvestmentTx.user_id == user.id,
                                   InvestmentTx.tx_type.in_(("buy", "sell")),
                                   InvestmentTx.symbol.isnot(None))
        .order_by(InvestmentTx.executed_at.asc().nullsfirst(), InvestmentTx.id.asc())
    )).scalars().all()
    quotes = {q.symbol: q for q in (await session.execute(select(InvestmentQuote))).scalars().all()}
    fx = {s: q.price for s, q in quotes.items() if len(s) == 6 and s.isalpha()}

    buys: dict[str, list[dict]] = {}
    sold: dict[str, float] = {}
    for t in txs:
        if t.tx_type == "buy":
            buys.setdefault(t.symbol, []).append({
                "qty": t.quantity or 0, "price": t.price or 0, "fee": t.fee or 0,
                "date": t.executed_at, "currency": t.currency or "USD", "name": t.name})
        else:
            sold[t.symbol] = sold.get(t.symbol, 0) + (t.quantity or 0)

    today = datetime.utcnow()
    lots = []
    sum_free = sum_pending = 0.0  # v base měně (CZK)
    complete = True
    for sym, lot_list in buys.items():
        remaining_to_sell = sold.get(sym, 0)
        for lot in lot_list:  # FIFO: nejstarší nákupy se prodávají první
            rem = lot["qty"]
            if remaining_to_sell > 0:
                take = min(rem, remaining_to_sell)
                rem -= take
                remaining_to_sell -= take
            if rem <= 1e-9 or not lot["date"]:
                continue
            free_date = _add_years(lot["date"], TIMETEST_YEARS)
            days = (free_date - today).days
            ccy = lot["currency"]
            cost = rem * lot["price"]
            q = quotes.get(sym)
            value = rem * q.price if q else None
            base_amt = _to_base(value if value is not None else cost, ccy, base, fx)
            if base_amt is None:
                complete = False
            elif days <= 0:
                sum_free += base_amt
            else:
                sum_pending += base_amt
            lots.append({
                "symbol": sym, "name": lot["name"], "quantity": round(rem, 6),
                "buy_date": lot["date"].date().isoformat(),
                "free_date": free_date.date().isoformat(),
                "days_remaining": days, "tax_free": days <= 0,
                "currency": ccy, "cost": round(cost, 2),
                "value": round(value, 2) if value is not None else None,
            })

    lots.sort(key=lambda x: x["days_remaining"])
    upcoming = [l for l in lots if 0 < l["days_remaining"] <= 365]
    return {
        "base": base, "years": TIMETEST_YEARS, "today": today.date().isoformat(),
        "lots": lots,
        "upcoming_12m": upcoming,
        "summary": {
            "value_tax_free": round(sum_free, 2),
            "value_pending": round(sum_pending, 2),
            "complete": complete,
            "n_tax_free": sum(1 for l in lots if l["tax_free"]),
            "n_pending": sum(1 for l in lots if not l["tax_free"]),
        },
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
        if _num(it.get("high_52w")) is not None:
            q.high_52w = _num(it.get("high_52w"))
        if _num(it.get("low_52w")) is not None:
            q.low_52w = _num(it.get("low_52w"))
        q.as_of = _parse_dt(it.get("as_of")) or datetime.utcnow()
        q.source = (it.get("source") or "yahoo")[:40]
        n += 1
    await session.commit()
    return {"status": "ok", "updated": n}


@router.post("/prices/history", dependencies=[Depends(_verify_token)])
async def ingest_history(payload: dict, session: AsyncSession = Depends(get_session)):
    """Upsert denní close historie symbolu (+ FX párů) pro křivku portfolia.
    payload = {"symbol": "AAPL", "bars": [{"date": "2026-01-02", "close": 180.1}, ...]}."""
    sym = (payload.get("symbol") or "").strip().upper()[:40]
    bars = payload.get("bars") or []
    if not sym or not isinstance(bars, list):
        raise HTTPException(status_code=400, detail="symbol + bars povinné")
    # existující datumy pro tento symbol (ať neinsertujeme duplicity)
    existing = set((await session.execute(
        select(InvestmentPriceDaily.date).where(InvestmentPriceDaily.symbol == sym)
    )).scalars().all())
    n = 0
    for b in bars:
        d = str(b.get("date") or "")[:10]
        c = _num(b.get("close"))
        if len(d) != 10 or c is None:
            continue
        if d in existing:
            row = await session.get(InvestmentPriceDaily, {"symbol": sym, "date": d})
            if row:
                row.close = c
        else:
            session.add(InvestmentPriceDaily(symbol=sym, date=d, close=c))
            existing.add(d)
        n += 1
    await session.commit()
    return {"status": "ok", "symbol": sym, "upserted": n}


@router.get("/curve")
async def portfolio_curve(days: int = Query(365, ge=7, le=3650),
                          base: str = Query(DEFAULT_BASE),
                          user: User = Depends(current_user),
                          session: AsyncSession = Depends(get_session)):
    """Časová řada hodnoty portfolia (market value) a vloženého kapitálu (cost basis).
    Pozn.: přepočet do base měny používá SOUČASNÝ FX (zjednodušení pro historii)."""
    base = base.strip().upper()[:8]
    txs = (await session.execute(
        select(InvestmentTx).where(InvestmentTx.user_id == user.id,
                                   InvestmentTx.tx_type.in_(("buy", "sell")),
                                   InvestmentTx.symbol.isnot(None),
                                   InvestmentTx.executed_at.isnot(None))
        .order_by(InvestmentTx.executed_at.asc()))).scalars().all()
    if not txs:
        return {"base": base, "points": [], "complete": True}

    symbols = {t.symbol for t in txs}
    quotes = {q.symbol: q for q in (await session.execute(select(InvestmentQuote))).scalars().all()}
    fx = {s: q.price for s, q in quotes.items() if len(s) == 6 and s.isalpha()}

    # Historie close per symbol → seřazené (date_str, close) pro bisect lookup ≤ date.
    hist_rows = (await session.execute(
        select(InvestmentPriceDaily).where(InvestmentPriceDaily.symbol.in_(symbols))
        .order_by(InvestmentPriceDaily.date.asc()))).scalars().all()
    hist: dict[str, list[tuple[str, float]]] = {}
    for r in hist_rows:
        hist.setdefault(r.symbol, []).append((r.date, r.close))

    def close_at(sym: str, dstr: str) -> float | None:
        arr = hist.get(sym)
        if not arr:
            q = quotes.get(sym)  # fallback: aktuální cena (lepší než nic)
            return q.price if q else None
        i = bisect.bisect_right([a[0] for a in arr], dstr)
        return arr[i - 1][1] if i > 0 else None

    end = date_cls.today()
    first = txs[0].executed_at.date()
    start = max(end - timedelta(days=days), first)
    span = (end - start).days or 1
    step = 1 if span <= 180 else (7 if span <= 1460 else 30)

    sample_dates: list[date_cls] = []
    d = start
    while d < end:
        sample_dates.append(d)
        d += timedelta(days=step)
    sample_dates.append(end)

    holdings: dict[str, dict] = {}
    ti, n_tx = 0, len(txs)
    points, complete = [], True
    for sd in sample_dates:
        while ti < n_tx and txs[ti].executed_at.date() <= sd:
            t = txs[ti]; ti += 1
            h = holdings.setdefault(t.symbol, {"qty": 0.0, "cost": 0.0, "ccy": t.currency or "USD"})
            q, pr, fee = t.quantity or 0, t.price or 0, t.fee or 0
            if t.tx_type == "buy":
                h["qty"] += q; h["cost"] += q * pr + fee
            else:
                avg = (h["cost"] / h["qty"]) if h["qty"] else 0
                h["cost"] -= avg * q; h["qty"] -= q
        dstr = sd.isoformat()
        invested = value = 0.0
        for sym, h in holdings.items():
            if h["qty"] <= 1e-9:
                continue
            rate = _to_base(1.0, h["ccy"], base, fx)
            if rate is None:
                complete = False
                continue
            invested += h["cost"] * rate
            pr = close_at(sym, dstr)
            if pr is None:
                complete = False
                continue
            value += h["qty"] * pr * rate
        points.append({"date": dstr, "invested": round(invested), "value": round(value)})

    return {"base": base, "points": points, "complete": complete, "step_days": step,
            "fx_note": "přepočet do CZK používá aktuální kurz"}
