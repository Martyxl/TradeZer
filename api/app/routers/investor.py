"""Jednoduchý režim (Začátečník) — profil investora, plán „Co teď udělat" a nápady.

GET /api/investor/profile   → režim UI, zvolený plán, měsíční vklad, rezerva (výchozí, když ještě neuložil)
PUT /api/investor/profile   → uloží změny (částečný update)
GET /api/investor/plan      → rozložení vs. plán, rozdělení měsíčního vkladu, seznam akcí, režim trhu + sentiment
GET /api/investor/ideas     → bezpečný základ (ETF) + levné kvalitní firmy + předražené

Nepřidává žádná nová data — skládá existující (portfolio, daňový test, Valuation Radar, režim trhu,
Smart Money fondy, Tradezer fond) do jednoduchých pravidel. Pokročilý režim se nemění.
"""
import json

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import InvestmentQuote, InvestmentSymbolMeta, InvestorProfile, User
from app.routers.auth import current_user
from app.routers.investments import _to_base, portfolio, tax_timetest
from app.routers.regime import get_regime
from app.services import investor_plan as P

router = APIRouter(prefix="/api/investor", tags=["investor"])
log = structlog.get_logger(__name__)

BASE = "CZK"
MODES = {"simple", "pro"}
MAX_CZK = 100_000_000


def _profile_out(p: InvestorProfile | None) -> dict:
    plan = p.plan if p else P.DEFAULT_PLAN
    return {
        "mode": p.mode if p else None,
        "plan": plan,
        "targets": P.plan_targets(plan, p.targets if p else None),
        "custom_targets": p.targets if p and p.plan == "custom" else None,
        "monthly_czk": p.monthly_czk if p else 5000,
        "reserve_czk": p.reserve_czk if p else 0,
        "saved": p is not None,
        "plans": {k: {"label": v["label"], "targets": v["targets"], "for": v["for"]} for k, v in P.PLANS.items()},
        "classes": P.CLASSES,
    }


@router.get("/profile")
async def get_profile(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    return _profile_out(await session.get(InvestorProfile, user.id))


def _money(v, field: str) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise HTTPException(422, f"{field}: číslo v Kč")
    if f < 0 or f > MAX_CZK or f != f:
        raise HTTPException(422, f"{field}: 0–{MAX_CZK:,} Kč".replace(",", " "))
    return round(f, 2)


@router.put("/profile")
async def put_profile(payload: dict = Body(...), user: User = Depends(current_user),
                      session: AsyncSession = Depends(get_session)):
    p = await session.get(InvestorProfile, user.id)
    if p is None:
        p = InvestorProfile(user_id=user.id, plan=P.DEFAULT_PLAN, monthly_czk=5000, reserve_czk=0)
        session.add(p)
    if "mode" in payload:
        if payload["mode"] not in MODES:
            raise HTTPException(422, "mode: simple | pro")
        p.mode = payload["mode"]
    if "plan" in payload:
        plan = payload["plan"]
        if plan not in (*P.PLANS, "custom"):
            raise HTTPException(422, "plan: careful | balanced | bold | custom")
        if plan == "custom":
            try:
                p.targets = P.validate_custom(payload.get("targets") or {})
            except ValueError as e:
                raise HTTPException(422, str(e))
        else:
            p.targets = None
        p.plan = plan
    if "monthly_czk" in payload:
        p.monthly_czk = _money(payload["monthly_czk"], "monthly_czk")
    if "reserve_czk" in payload:
        p.reserve_czk = _money(payload["reserve_czk"], "reserve_czk")
    await session.commit()
    return _profile_out(p)


async def _fx_and_quotes(session: AsyncSession) -> tuple[dict, dict]:
    quotes = {q.symbol: q for q in (await session.execute(select(InvestmentQuote))).scalars().all()}
    fx = {s: q.price for s, q in quotes.items() if len(s) == 6 and s.isalpha()}
    return quotes, fx


def _price_czk(sym: str, quotes: dict, fx: dict, currency: str | None = None) -> float | None:
    q = quotes.get(sym)
    if not q:
        return None
    return _to_base(q.price, currency or q.currency or "USD", BASE, fx)


async def _ideas(session: AsyncSession, held: set[str]) -> dict:
    rows, as_of = [], None
    try:
        from app.valuation.models import ValOverviewSnapshot
        snap = await session.get(ValOverviewSnapshot, "latest")
        if snap:
            rows, as_of = (snap.payload or {}).get("items", []), snap.as_of_date
    except Exception as e:  # noqa: BLE001 — bez valuací jen prázdné nápady
        log.warning("investor: overview unavailable", error=str(e))
    fund_buyers: dict[str, int] = {}
    try:
        from app.models import SmartMoneySnapshot
        sm = await session.scalar(select(SmartMoneySnapshot).where(SmartMoneySnapshot.name == "funds"))
        if sm:
            for e in (json.loads(sm.payload) or {}).get("consensus_buys", []):
                if e.get("ticker"):
                    fund_buyers[e["ticker"].upper()] = int(e.get("count") or 0)
    except Exception as e:  # noqa: BLE001
        log.warning("investor: funds snapshot unavailable", error=str(e))
    house: set[str] = set()
    try:
        from app.models import FundPosition
        house = {P.base_symbol(s) for s in (await session.execute(select(FundPosition.symbol))).scalars().all()}
    except Exception as e:  # noqa: BLE001
        log.warning("investor: house fund unavailable", error=str(e))
    out = P.ideas_from_overview(rows, held={P.base_symbol(h) for h in held}, fund_buyers=fund_buyers, house=house)
    out["as_of"] = as_of.isoformat() if as_of else None
    return out


@router.get("/ideas")
async def ideas(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    quotes, fx = await _fx_and_quotes(session)
    pf = await portfolio(base=BASE, user=user, session=session)
    held = {h["symbol"] for h in pf["holdings"]}
    base = []
    for u in P.UNIVERSE:
        q = quotes.get(u["symbol"])
        base.append({**u, "class_label": P.CLASSES[u["cls"]], "held": u["symbol"] in held,
                     "price": q.price if q else None, "price_currency": (q.currency if q else None) or u["currency"],
                     "price_czk": _price_czk(u["symbol"], quotes, fx, u["currency"]),
                     "high_52w": q.high_52w if q else None, "low_52w": q.low_52w if q else None})
    return {"base": base, **(await _ideas(session, held))}


@router.get("/plan")
async def plan(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    prof = await session.get(InvestorProfile, user.id)
    plan_key = prof.plan if prof else P.DEFAULT_PLAN
    targets = P.plan_targets(plan_key, prof.targets if prof else None)
    monthly = prof.monthly_czk if prof else 5000
    reserve = prof.reserve_czk if prof else 0

    pf = await portfolio(base=BASE, user=user, session=session)
    tt = await tax_timetest(base=BASE, user=user, session=session)
    quotes, fx = await _fx_and_quotes(session)
    syms = [h["symbol"].upper() for h in pf["holdings"]]
    metas = {m.symbol: m.data for m in (await session.execute(
        select(InvestmentSymbolMeta).where(InvestmentSymbolMeta.symbol.in_(syms)))).scalars().all()} if syms else {}

    total = pf["base_totals"]["value"] or 0
    positions = []
    for h in pf["holdings"]:
        w = h.get("weight_pct")
        positions.append({
            "symbol": h["symbol"], "name": h.get("name"), "quantity": h["quantity"],
            "cls": P.classify(h["symbol"], h.get("name"), metas.get(h["symbol"].upper())),
            "value_base": round(w / 100 * total, 2) if (w is not None and total) else None,
            "weight": w, "unrealized_pct": h.get("unrealized_pct"), "signal": h["signal"],
        })
    alloc = P.allocation(positions, targets, reserve)
    contribution = P.split_contribution(alloc, targets, monthly)
    idea = await _ideas(session, set(syms))
    prices = {}
    for c in contribution:
        cand = [p["symbol"] for p in positions if p["cls"] == c] or ([P.DEFAULT_INSTRUMENT[c]["symbol"]] if c in P.DEFAULT_INSTRUMENT else [])
        cand += [i["ticker"] for i in idea["cheap"][:1]] if c == "stocks" else []
        for s in cand:
            pc = _price_czk(s, quotes, fx)
            if pc:
                prices[s] = pc
    actions = P.build_actions(positions=positions, alloc=alloc, targets=targets, contribution=contribution,
                              lots=tt["lots"], ideas=idea["cheap"], prices_czk=prices)
    for a in actions:  # předvyplnění „Zapsat nákup": aktuální cena v měně titulu
        q = quotes.get(a.get("symbol") or "") if a["kind"] == "buy" else None
        if q:
            a["price"], a["currency"] = q.price, q.currency

    # pozice pro jednoduchou tabulku: štítek (koupit/ubrat/počkat/držet) + nejbližší osvobození od daně
    free_by: dict[str, str] = {}      # nejbližší datum osvobození u lotů, které ještě v testu jsou
    free_some: set[str] = set()        # symboly, kde je část nákupů už bez daně
    for lt in tt["lots"]:
        if lt["tax_free"]:
            free_some.add(lt["symbol"])
        else:
            free_by[lt["symbol"]] = min(free_by.get(lt["symbol"], lt["free_date"]), lt["free_date"])
    tag_by = {}
    for a in actions:
        if a.get("symbol") and a["kind"] in ("buy", "trim", "wait"):
            tag_by.setdefault(a["symbol"], a["kind"])
    simple_positions = sorted(({
        "symbol": p["symbol"], "name": p["name"], "cls": p["cls"], "class_label": P.CLASSES[p["cls"]],
        "value": p["value_base"], "weight": p["weight"], "unrealized_pct": p["unrealized_pct"],
        "tag": tag_by.get(p["symbol"], "hold"), "tax_free_from": free_by.get(p["symbol"]),
        "tax_free_all": p["symbol"] not in free_by,
        "tax_free_part": p["symbol"] in free_by and p["symbol"] in free_some,
    } for p in positions), key=lambda x: -(x["value"] or 0))

    regime = await get_regime(session=session)
    return {
        "profile": _profile_out(prof),
        "totals": {**pf["base_totals"], "tax_free": tt["summary"]["value_tax_free"],
                   "tax_pending": tt["summary"]["value_pending"], "reserve": reserve},
        "allocation": alloc,
        "contribution": [{"cls": c, "label": P.CLASSES[c], "amount": a} for c, a in contribution.items()],
        "actions": actions,
        "positions": simple_positions,
        "market": P.market_block(regime),
    }
