"""Discovery screener — čtení posledního snapshotu + push z lokálního skeneru.

GET  /api/discovery         → poslední výsledek momentum screeneru (veřejné, čtení)
POST /api/discovery/ingest  → uloží nový snapshot (token; volá `data/discovery_scan.py --push`)

Snapshot je 1 JSON blob v DB (DiscoverySnapshot name="latest"). Sken běží z rezidenční
IP (Yahoo blokuje datacentra), Vercel na Spark nedosáhne → push-only vzor jako predictor.
"""
import json
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Body, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import DiscoverySnapshot
from app.routers.admin import _verify_token

router = APIRouter(prefix="/api/discovery", tags=["discovery"])
log = structlog.get_logger(__name__)

_SNAPSHOT_NAME = "latest"


@router.get("")
async def get_discovery(session: AsyncSession = Depends(get_session)):
    """Poslední snapshot screeneru. Když ještě žádný neexistuje, vrátí prázdnou obálku
    (frontend zobrazí výzvu spustit sken) — nikdy nespadne."""
    row = await session.scalar(
        select(DiscoverySnapshot).where(DiscoverySnapshot.name == _SNAPSHOT_NAME)
    )
    if not row:
        return {"generated": None, "universe_size": 0, "scanned": 0,
                "note": "Zatím žádný snapshot. Spusť data/discovery_scan.py --push.",
                "items": []}
    try:
        return json.loads(row.payload)
    except (ValueError, TypeError):
        return {"generated": None, "universe_size": 0, "scanned": 0,
                "note": "Poškozený snapshot.", "items": []}


@router.post("/ingest", dependencies=[Depends(_verify_token)])
async def ingest_discovery(
    payload: dict = Body(...),
    session: AsyncSession = Depends(get_session),
):
    """Uloží/přepíše poslední snapshot. Payload = výstup discovery_scan (dict s `items`).
    Idempotentní upsert do jednoho řádku (žádné accumulování)."""
    items = payload.get("items")
    if not isinstance(items, list):
        return {"status": "error", "detail": "payload musí obsahovat pole 'items'"}
    # Server-side timestamp jako pojistka, když ho skener nepošle.
    payload.setdefault("generated", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    text = json.dumps(payload, ensure_ascii=False)

    row = await session.scalar(
        select(DiscoverySnapshot).where(DiscoverySnapshot.name == _SNAPSHOT_NAME)
    )
    if row:
        row.payload = text
    else:
        session.add(DiscoverySnapshot(name=_SNAPSHOT_NAME, payload=text))
    await session.commit()
    log.info("Discovery snapshot uložen", items=len(items))
    return {"status": "ok", "items": len(items)}
