"""Gamma exposure (GEX) — čtení posledního snapshotu + push z lokálního skeneru.

GET  /api/gamma[?ticker=NQ]  → celý snapshot, nebo jen 1 instrument (veřejné čtení)
POST /api/gamma/ingest       → uloží nový snapshot (token; volá `data/gamma_scan.py --push`)

Snapshot je 1 JSON blob v DB (GammaSnapshot name="latest"). Sken běží z rezidenční IP
(Yahoo options blokuje datacentra), Vercel na Spark nedosáhne → push-only vzor.
"""
import json
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import GammaSnapshot
from app.routers.admin import _verify_token

router = APIRouter(prefix="/api/gamma", tags=["gamma"])
log = structlog.get_logger(__name__)

_SNAPSHOT_NAME = "latest"


async def _load(session: AsyncSession) -> dict:
    row = await session.scalar(
        select(GammaSnapshot).where(GammaSnapshot.name == _SNAPSHOT_NAME)
    )
    if not row:
        return {"generated": None, "instruments": {},
                "note": "Zatím žádný snapshot. Spusť data/gamma_scan.py --push."}
    try:
        return json.loads(row.payload)
    except (ValueError, TypeError):
        return {"generated": None, "instruments": {}, "note": "Poškozený snapshot."}


@router.get("")
async def get_gamma(
    ticker: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    """Poslední GEX snapshot. S ?ticker= vrátí jen ten instrument (nebo prázdný objekt)."""
    data = await _load(session)
    if ticker:
        inst = (data.get("instruments") or {}).get(ticker.upper())
        return {"generated": data.get("generated"), "ticker": ticker.upper(),
                "instrument": inst, "note": data.get("note")}
    return data


@router.post("/ingest", dependencies=[Depends(_verify_token)])
async def ingest_gamma(
    payload: dict = Body(...),
    session: AsyncSession = Depends(get_session),
):
    """Uloží/přepíše poslední snapshot. Payload = výstup gamma_scan (dict s `instruments`)."""
    instruments = payload.get("instruments")
    if not isinstance(instruments, dict):
        return {"status": "error", "detail": "payload musí obsahovat objekt 'instruments'"}
    payload.setdefault("generated", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    text = json.dumps(payload, ensure_ascii=False)

    row = await session.scalar(
        select(GammaSnapshot).where(GammaSnapshot.name == _SNAPSHOT_NAME)
    )
    if row:
        row.payload = text
    else:
        session.add(GammaSnapshot(name=_SNAPSHOT_NAME, payload=text))
    await session.commit()
    log.info("Gamma snapshot uložen", instruments=len(instruments))
    return {"status": "ok", "instruments": len(instruments)}
