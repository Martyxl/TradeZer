"""Jednoduchý režim (Začátečník) — profil investora, plán „Co teď udělat" a nápady.

GET /api/investor/profile   → režim UI, zvolený plán, měsíční vklad, rezerva (výchozí, když ještě neuložil)
PUT /api/investor/profile   → uloží změny (částečný update)
GET /api/investor/plan      → rozložení vs. plán, rozdělení měsíčního vkladu, seznam akcí, režim trhu + sentiment
GET /api/investor/ideas     → bezpečný základ (ETF) + levné kvalitní firmy + předražené

Nepřidává žádná nová data — skládá existující (portfolio, daňový test, Valuation Radar, režim trhu,
Smart Money fondy, Tradezer fond) do jednoduchých pravidel. Pokročilý režim se nemění.
"""
import json
from datetime import datetime

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import InvestmentQuote, InvestmentSymbolMeta, InvestmentTx, InvestorProfile, User
from app.routers.auth import current_user
from app.routers.investments import _to_base, portfolio, tax_timetest
from app.routers.regime import get_regime
from app.services import investor_plan as P

router = APIRouter(prefix="/api/investor", tags=["investor"])
log = structlog.get_logger(__name__)

BASE = "CZK"
MODES = {"simple", "pro"}
MAX_CZK = 100_000_000


def _profile_out(p: InvestorProfile | None, capital_left: float | None = None) -> dict:
    plan = p.plan if p else P.DEFAULT_PLAN
    capital = (p.capital_czk or 0) if p else 0
    return {
        "mode": p.mode if p else None,
        "plan": plan,
        "targets": P.plan_targets(plan, p.targets if p else None),
        "custom_targets": p.targets if p and p.plan == "custom" else None,
        "monthly_czk": p.monthly_czk if p else 5000,
        "reserve_czk": p.reserve_czk if p else 0,
        # volné peníze: zadaná částka a kolik z ní zbývá po nákupech zapsaných od jejího zadání
        "capital_czk": capital,
        "capital_left": round(capital if capital_left is None else capital_left, 2),
        "capital_set_at": p.capital_set_at.isoformat() if p and p.capital_set_at else None,
        "saved": p is not None,
        "plan_set": bool(p and p.plan_set_at),
        "plans": {k: {"label": v["label"], "targets": v["targets"], "for": v["for"]} for k, v in P.PLANS.items()},
        "classes": P.CLASSES,
    }


async def _capital_left(session: AsyncSession, p: InvestorProfile | None, fx: dict) -> float:
    """Volné peníze − nákupy (+ výnosy z prodejů) zapsané od zadání částky. Starší transakce z importu
    výpisu (datum obchodu před zadáním) se nepočítají. Bez kurzu se transakce přeskočí."""
    if not p or not p.capital_czk or not p.capital_set_at:
        return (p.capital_czk or 0) if p else 0
    since = p.capital_set_at
    txs = (await session.execute(select(InvestmentTx).where(
        InvestmentTx.user_id == p.user_id, InvestmentTx.tx_type.in_(("buy", "sell")),
        InvestmentTx.id > (p.capital_after_tx or 0)))).scalars().all()
    spent = 0.0
    for t in txs:
        if t.executed_at and t.executed_at.date() < since.date():
            continue
        gross = (t.quantity or 0) * (t.price or 0)
        v = _to_base(gross + (t.fee or 0) if t.tx_type == "buy" else -(gross - (t.fee or 0)), t.currency or "USD", BASE, fx)
        spent += v or 0
    return max(0.0, p.capital_czk - spent)


@router.get("/profile")
async def get_profile(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    p = await session.get(InvestorProfile, user.id)
    _, fx = await _fx_and_quotes(session)
    return _profile_out(p, await _capital_left(session, p, fx))


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
            raise HTTPException(422, "plan: " + " | ".join((*P.PLANS, "custom")))
        if plan == "custom":
            try:
                p.targets = P.validate_custom(payload.get("targets") or {})
            except ValueError as e:
                raise HTTPException(422, str(e))
        else:
            p.targets = None
        p.plan = plan
        p.plan_set_at = datetime.utcnow()
    if "monthly_czk" in payload:
        p.monthly_czk = _money(payload["monthly_czk"], "monthly_czk")
    if "reserve_czk" in payload:
        p.reserve_czk = _money(payload["reserve_czk"], "reserve_czk")
    if "capital_czk" in payload:  # nová částka = nový začátek odečítání nákupů
        p.capital_czk = _money(payload["capital_czk"], "capital_czk")
        p.capital_set_at = datetime.utcnow()
        p.capital_after_tx = await session.scalar(
            select(func.max(InvestmentTx.id)).where(InvestmentTx.user_id == user.id)) or 0
    await session.commit()
    _, fx = await _fx_and_quotes(session)
    return _profile_out(p, await _capital_left(session, p, fx))


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
    capital_left = await _capital_left(session, prof, fx)
    invest_now = monthly + capital_left  # tento měsíc: pravidelný vklad + zbývající volné peníze
    contribution = P.split_contribution(alloc, targets, invest_now)
    contribution, stocks_deferred = P.fit_to_size(contribution, alloc["total"] + invest_now)
    idea = await _ideas(session, set(syms))
    prices = {}
    for c in contribution:
        cand = [p["symbol"] for p in positions if p["cls"] == c] or ([P.DEFAULT_INSTRUMENT[c]["symbol"]] if c in P.DEFAULT_INSTRUMENT else [])
        cand += [i["ticker"] for i in idea["cheap"][:4]] if c == "stocks" else []
        for s in cand:
            pc = _price_czk(s, quotes, fx)
            if pc:
                prices[s] = pc
    actions = P.build_actions(positions=positions, alloc=alloc, targets=targets, contribution=contribution,
                              lots=tt["lots"], ideas=idea["cheap"], prices_czk=prices, stocks_deferred=stocks_deferred)
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
        "profile": _profile_out(prof, capital_left),
        "invest_now": {"total": round(invest_now, 2), "monthly": monthly, "capital": round(capital_left, 2),
                       "hint": P.capital_hint(capital_left, monthly, (regime or {}).get("state"))},
        "totals": {**pf["base_totals"], "tax_free": tt["summary"]["value_tax_free"],
                   "tax_pending": tt["summary"]["value_pending"], "reserve": reserve},
        "allocation": alloc,
        "contribution": [{"cls": c, "label": P.CLASSES[c], "amount": a} for c, a in contribution.items()],
        "actions": actions,
        "positions": simple_positions,
        "market": P.market_block(regime),
    }


# ── Jednoduchý Radar: seznam firem a zjednodušená karta firmy ────────────────
# Stejná data a stejný tarif jako Valuation Radar (Trader) — jen jinak podané.
from app.routers.auth import require_plan  # noqa: E402
from app.services import company_explain as X  # noqa: E402


async def _overview_rows(session: AsyncSession) -> tuple[list[dict], object]:
    from app.valuation.models import ValOverviewSnapshot
    snap = await session.get(ValOverviewSnapshot, "latest")
    return ((snap.payload or {}).get("items", []), snap.as_of_date) if snap else ([], None)


async def _held_weights(user: User, session: AsyncSession) -> dict[str, float | None]:
    pf = await portfolio(base=BASE, user=user, session=session)
    return {P.base_symbol(h["symbol"]): h.get("weight_pct") for h in pf["holdings"]}


@router.get("/radar")
async def radar(user: User = Depends(require_plan("trader")), session: AsyncSession = Depends(get_session)):
    rows, as_of = await _overview_rows(session)
    held = await _held_weights(user, session)
    items = []
    for r in rows:
        t = (r.get("ticker") or "").upper()
        if not t:
            continue
        rel, _ = P.zone_reliability(r.get("eps_growth_ntm"), r.get("growth_basis"), r.get("confidence"))
        items.append({
            "ticker": t, "name": r.get("name"), "verdict": r.get("valuation_verdict"),
            "verdict_label": X.VERDICT_CS.get((r.get("valuation_verdict") or "").upper()),
            "bucket": X.bucket(r.get("valuation_verdict"), bool(r.get("bubble_flag"))),
            "zone": P.zone(r.get("pctile_pe_fwd"), r.get("eps_growth_ntm")),
            "reliable": bool(rel) and (r.get("confidence") or 0) >= 0.5,
            "text": P._idea_text(r), "held": t in held, "market_cap": r.get("market_cap"),
            "score": r.get("composite_score"),
            # pro mapu zón (stejné osy jako Valuation Radar)
            "pctile_pe_fwd": r.get("pctile_pe_fwd"), "eps_growth_ntm": r.get("eps_growth_ntm"),
            "bubble_flag": bool(r.get("bubble_flag")), "confidence": r.get("confidence"),
        })
    items.sort(key=lambda i: -(i["market_cap"] or 0))
    from app.valuation.zones import zone_curves
    return {"as_of": as_of.isoformat() if as_of else None, "items": items, "zones": zone_curves()}


@router.get("/radar/{ticker}")
async def radar_company(ticker: str, user: User = Depends(require_plan("trader")),
                        session: AsyncSession = Depends(get_session)):
    from datetime import date as _date
    from app.config import settings
    from app.valuation.models import ValEarningsUpcoming, ValInstrument, ValMetricsDaily, ValScoreDaily
    t = ticker.strip().upper()[:12]
    version = settings.val_model_version
    inst = await session.scalar(select(ValInstrument).where(ValInstrument.ticker == t))
    score = await session.scalar(select(ValScoreDaily).where(
        ValScoreDaily.ticker == t, ValScoreDaily.model_version == version)
        .order_by(ValScoreDaily.as_of_date.desc()).limit(1))
    if inst is None and score is None:
        raise HTTPException(404, f"Firmu {t} Radar nesleduje")
    metrics = {}
    if score:
        m = await session.scalar(select(ValMetricsDaily).where(
            ValMetricsDaily.ticker == t, ValMetricsDaily.as_of_date == score.as_of_date,
            ValMetricsDaily.model_version == version))
        metrics = (m.metrics if m else {}) or {}
    rows, _ = await _overview_rows(session)
    row = next((r for r in rows if (r.get("ticker") or "").upper() == t), {})
    nxt = await session.scalar(select(ValEarningsUpcoming).where(
        ValEarningsUpcoming.ticker == t, ValEarningsUpcoming.report_date >= _date.today())
        .order_by(ValEarningsUpcoming.report_date.asc()).limit(1))

    s = score
    view = X.explain(
        scores={"valuation": s and s.valuation_score, "growth": s and s.growth_score, "quality": s and s.quality_score,
                "revision": s and s.revision_score, "trend": s and s.trend_score, "composite": s and s.composite_score},
        metrics=metrics, drivers=(s.drivers if s and s.drivers else {}),
        verdict=s.valuation_verdict if s else None, horizon=s.horizon_verdict if s else None,
        bubble=bool(s and s.bubble_flag), confidence=s.confidence if s else None,
        growth_basis=row.get("growth_basis"))

    held = await _held_weights(user, session)
    prof = await session.get(InvestorProfile, user.id)
    plan_key = prof.plan if prof else P.DEFAULT_PLAN
    targets = P.plan_targets(plan_key, prof.targets if prof else None)
    plan_label = "Vlastní" if plan_key == "custom" else P.PLANS.get(plan_key, P.PLANS[P.DEFAULT_PLAN])["label"]
    return {
        "ticker": t, "name": inst.name if inst else row.get("name"),
        "sector": inst.gics_sector if inst else None, "industry": inst.gics_industry if inst else None,
        "as_of": s.as_of_date.isoformat() if s else None,
        "held": t in held, "weight": held.get(t),
        "next_earnings": nxt.report_date.isoformat() if nxt else None,
        **view,
        "advice": X.advice(bucket_=view["bucket"], zone_=view["zone"], reliable=view["reliable"],
                           held_weight=(held.get(t) or 0.0) if t in held else None,
                           stocks_target=targets.get("stocks", 0), plan_label=plan_label),
    }


# ── Sezónnost (Přehled) ─────────────────────────────────────────────────────
from datetime import date as _date  # noqa: E402

from fastapi import Query  # noqa: E402

from app.models import InvestmentPriceDaily  # noqa: E402
from app.services import seasonality as S  # noqa: E402

MAX_SEASON_SYMBOLS = 12


@router.get("/seasonality")
async def seasonality(symbols: str = Query(..., max_length=600), user: User = Depends(current_user),
                      session: AsyncSession = Depends(get_session)):
    """Sezónnost posledních 3 let pro symboly z Přehledu. Zdroj: denní ceny portfolia
    (InvestmentPriceDaily, ETF + držené tituly); když tam jsou kratší, denní ceny Valuation Radaru."""
    from app.valuation.models import ValPriceDaily
    syms = list(dict.fromkeys(s.strip().upper()[:40] for s in symbols.split(",") if s.strip()))[:MAX_SEASON_SYMBOLS]
    years = S.season_years(_date.today())
    since = f"{years[0] - 1}-{S.PREV_FROM_DAY}"
    bars: dict[str, list[tuple[str, float]]] = {s: [] for s in syms}
    for r in (await session.execute(
        select(InvestmentPriceDaily.symbol, InvestmentPriceDaily.date, InvestmentPriceDaily.close)
        .where(InvestmentPriceDaily.symbol.in_(syms), InvestmentPriceDaily.date >= since)
        .order_by(InvestmentPriceDaily.date.asc())
    )).all():
        bars[r.symbol].append((r.date, r.close))
    curves = {s: S.year_curves(bars[s], years) for s in syms}
    # Akcie z Valuation Radaru mají historii roky zpět — použij, pokud dá víc let.
    short = {P.base_symbol(s): s for s in syms if len(curves[s]) < len(years)}
    if short:
        val: dict[str, list[tuple[str, float]]] = {t: [] for t in short}
        for r in (await session.execute(
            select(ValPriceDaily.ticker, ValPriceDaily.date, ValPriceDaily.close, ValPriceDaily.adj_close)
            .where(ValPriceDaily.ticker.in_(list(short)), ValPriceDaily.date >= _date.fromisoformat(since))
            .order_by(ValPriceDaily.date.asc())
        )).all():
            c = r.adj_close or r.close
            if c:
                val[r.ticker].append((r.date.isoformat(), c))
        for t, s in short.items():
            alt = S.year_curves(val[t], years)
            if len(alt) > len(curves[s]):
                curves[s] = alt
    return {
        "years": years,
        "items": [{"symbol": s, "years": curves[s]} for s in syms],
    }
