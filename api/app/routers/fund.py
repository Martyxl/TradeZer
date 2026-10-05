"""TRADEZER investuje — AI paper-trading fond.

GET  /api/fund          → stav + pozice + obchody + equity křivka (VEŘEJNÉ, showcase)
GET  /api/fund/signals  → agregované naše analýzy pro algoritmus (interní token)
POST /api/fund/ingest   → Spark pushne zrcadlo stavu (interní token)

Autoritativní stav je na Sparku; tohle je display kopie pro frontend.
"""
import json

import structlog
from fastapi import APIRouter, Body, Depends
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import (FundState, FundPosition, FundTrade, FundSnapshot,
                        DiscoverySnapshot, SmartMoneySnapshot, DarkPoolSnapshot)
from app.routers.admin import _verify_token

router = APIRouter(prefix="/api/fund", tags=["fund"])
log = structlog.get_logger(__name__)


@router.get("")
async def get_fund(session: AsyncSession = Depends(get_session)):
    """Veřejný pohled na fond TRADEZERu (showcase)."""
    st = await session.get(FundState, 1)
    if st is None:
        return {"state": None, "positions": [], "trades": [], "snapshots": [],
                "note": "Fond ještě nezačal obchodovat."}
    positions = (await session.execute(
        select(FundPosition).order_by(FundPosition.value_czk.desc().nullslast()))).scalars().all()
    trades = (await session.execute(
        select(FundTrade).order_by(FundTrade.ts.desc()).limit(120))).scalars().all()
    snaps = (await session.execute(
        select(FundSnapshot).order_by(FundSnapshot.date.asc()))).scalars().all()
    pnl = st.equity - st.start_capital
    return {
        "state": {
            "start_capital": st.start_capital, "cash": st.cash, "equity": st.equity,
            "base": st.base, "as_of": st.as_of.isoformat() if st.as_of else None,
            "note": st.note, "pnl": round(pnl), "pnl_pct": round(pnl / st.start_capital * 100, 2) if st.start_capital else 0,
        },
        "positions": [{
            "symbol": p.symbol, "name": p.name, "quantity": p.quantity, "avg_cost": p.avg_cost,
            "currency": p.currency, "last_price": p.last_price, "value_czk": p.value_czk,
            "unrealized_czk": p.unrealized_czk, "weight_pct": p.weight_pct,
            "opened_at": p.opened_at, "conviction": p.conviction,
        } for p in positions],
        "trades": [{
            "ts": t.ts, "action": t.action, "symbol": t.symbol, "name": t.name,
            "quantity": t.quantity, "price": t.price, "currency": t.currency,
            "value_czk": t.value_czk, "realized_czk": t.realized_czk,
            "conviction": t.conviction, "reason": t.reason,
        } for t in trades],
        "snapshots": [{"date": s.date, "equity": s.equity, "cash": s.cash,
                       "invested": s.invested, "benchmark": s.benchmark} for s in snaps],
    }


def _payload(row) -> dict:
    try:
        return json.loads(row.payload) if row else {}
    except (ValueError, TypeError):
        return {}


@router.get("/signals", dependencies=[Depends(_verify_token)])
async def fund_signals(session: AsyncSession = Depends(get_session)):
    """Agregované analýzy pro algoritmus fondu (interní token). Valuace + discovery
    + smart money + dark pool v kompaktní podobě."""
    from app.valuation.models import ValOverviewSnapshot
    val = await session.get(ValOverviewSnapshot, "latest")
    valuation = []
    if val and val.payload:
        for it in val.payload.get("items", []):
            valuation.append({"ticker": it.get("ticker"), "name": it.get("name"),
                              "verdict": it.get("valuation_verdict"), "horizon": it.get("horizon_verdict"),
                              "composite": it.get("composite_score"), "pctile_pe": it.get("pctile_pe_fwd"),
                              "market_cap": it.get("market_cap"), "confidence": it.get("confidence")})
    disc = _payload(await session.scalar(select(DiscoverySnapshot).where(DiscoverySnapshot.name == "latest")))
    sm = _payload(await session.scalar(select(SmartMoneySnapshot).where(SmartMoneySnapshot.name == "latest")))
    dp = _payload(await session.scalar(select(DarkPoolSnapshot).where(DarkPoolSnapshot.name == "latest")))
    return {
        "valuation": valuation,
        "discovery": (disc.get("items") or [])[:60],
        "smart_money_top_buys": sm.get("top_buys") or [],
        "smart_money_insiders": (sm.get("insiders") or [])[:60],
        "dark_pool": (dp.get("items") or [])[:40],
    }


@router.post("/ingest", dependencies=[Depends(_verify_token)])
async def ingest_fund(payload: dict = Body(...), session: AsyncSession = Depends(get_session)):
    """Spark pushne kompletní zrcadlo: {state, positions, trades, snapshots}.
    Pozice a obchody se přepíšou celé (Spark je zdroj pravdy), snapshoty upsert dle data."""
    from datetime import datetime
    s = payload.get("state") or {}
    st = await session.get(FundState, 1)
    if st is None:
        st = FundState(id=1)
        session.add(st)
    st.start_capital = float(s.get("start_capital", 1_000_000))
    st.cash = float(s.get("cash", st.cash))
    st.equity = float(s.get("equity", st.equity))
    st.base = s.get("base", "CZK")[:8]
    st.note = s.get("note")
    try:
        st.as_of = datetime.fromisoformat(s["as_of"]) if s.get("as_of") else datetime.utcnow()
    except (ValueError, TypeError):
        st.as_of = datetime.utcnow()

    await session.execute(delete(FundPosition))
    for p in payload.get("positions") or []:
        session.add(FundPosition(
            symbol=str(p.get("symbol"))[:24], name=(p.get("name") or None),
            quantity=float(p.get("quantity", 0)), avg_cost=float(p.get("avg_cost", 0)),
            currency=(p.get("currency") or "USD")[:8], last_price=p.get("last_price"),
            value_czk=p.get("value_czk"), unrealized_czk=p.get("unrealized_czk"),
            weight_pct=p.get("weight_pct"), opened_at=(p.get("opened_at") or None),
            conviction=p.get("conviction")))

    await session.execute(delete(FundTrade))
    for t in (payload.get("trades") or [])[:600]:
        session.add(FundTrade(
            ts=str(t.get("ts"))[:19], action=(t.get("action") or "buy")[:8],
            symbol=str(t.get("symbol"))[:24], name=(t.get("name") or None),
            quantity=float(t.get("quantity", 0)), price=float(t.get("price", 0)),
            currency=(t.get("currency") or "USD")[:8], value_czk=t.get("value_czk"),
            realized_czk=t.get("realized_czk"), conviction=t.get("conviction"),
            reason=str(t.get("reason") or "")))

    for sn in payload.get("snapshots") or []:
        d = str(sn.get("date"))[:10]
        if len(d) != 10:
            continue
        row = await session.get(FundSnapshot, d)
        if row is None:
            row = FundSnapshot(date=d, equity=0, cash=0, invested=0)
            session.add(row)
        row.equity = float(sn.get("equity", 0))
        row.cash = float(sn.get("cash", 0))
        row.invested = float(sn.get("invested", 0))
        row.benchmark = sn.get("benchmark")

    await session.commit()
    return {"status": "ok", "positions": len(payload.get("positions") or []),
            "trades": len(payload.get("trades") or [])}
