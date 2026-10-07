"""Režim trhu — čtení posledního snapshotu + push ze skeneru na Sparku.

GET  /api/regime         → {state, label, reasons, indicators, geo, as_of} (veřejné čtení)
POST /api/regime/ingest  → uloží nový snapshot (token; volá `data/risk_regime.py --push`)

State: calm | recovering | tension | panic. Chybí-li data, vrací state=null (UI kartu skryje).
"""
import json
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Body, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import RegimeSnapshot
from app.routers.admin import _verify_token

router = APIRouter(prefix="/api/regime", tags=["regime"])
log = structlog.get_logger(__name__)

_NAME = "latest"
STATES = {"calm", "recovering", "tension", "panic"}


@router.get("")
async def get_regime(session: AsyncSession = Depends(get_session)):
    row = await session.scalar(select(RegimeSnapshot).where(RegimeSnapshot.name == _NAME))
    if not row:
        return {"state": None, "note": "Zatím žádný snapshot. Spusť data/risk_regime.py --push."}
    try:
        return json.loads(row.payload)
    except (ValueError, TypeError):
        return {"state": None, "note": "Poškozený snapshot."}


@router.post("/ingest", dependencies=[Depends(_verify_token)])
async def ingest_regime(payload: dict = Body(...), session: AsyncSession = Depends(get_session)):
    if payload.get("state") not in STATES:
        return {"status": "error", "detail": f"state musí být jedno z {sorted(STATES)}"}
    payload.setdefault("as_of", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    text = json.dumps(payload, ensure_ascii=False)
    row = await session.scalar(select(RegimeSnapshot).where(RegimeSnapshot.name == _NAME))
    if row:
        row.payload = text
    else:
        session.add(RegimeSnapshot(name=_NAME, payload=text))
    await session.commit()
    log.info("Regime snapshot uložen", state=payload["state"])
    return {"status": "ok", "state": payload["state"]}
