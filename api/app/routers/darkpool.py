"""Dark Pool — FINRA ATS (off-exchange / „dark pool") týdenní objemy per symbol.

GET  /api/darkpool         → poslední snapshot (Pro+)
POST /api/darkpool/ingest  → uloží snapshot (token; volá `data/finra_darkpool_scan.py --push`)

Data z veřejného FINRA OTC Transparency API (ATS_W_SMBL), bez auth. Týdenní,
s ~měsíčním zpožděním publikace. 1 JSON blob v DB (DarkPoolSnapshot name="latest").
"""
import json
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Body, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import DarkPoolSnapshot
from app.routers.admin import _verify_token
from app.routers.auth import require_plan

router = APIRouter(prefix="/api/darkpool", tags=["darkpool"])
log = structlog.get_logger(__name__)

_SNAPSHOT_NAME = "latest"
_EMPTY = {"generated": None, "week": None, "count": 0, "items": [],
          "note": "Zatím žádný snapshot. Spusť data/finra_darkpool_scan.py --push."}


@router.get("", dependencies=[Depends(require_plan("pro"))])
async def get_darkpool(session: AsyncSession = Depends(get_session)):
    row = await session.scalar(
        select(DarkPoolSnapshot).where(DarkPoolSnapshot.name == _SNAPSHOT_NAME)
    )
    if not row:
        return _EMPTY
    try:
        return json.loads(row.payload)
    except (ValueError, TypeError):
        return {**_EMPTY, "note": "Poškozený snapshot."}


@router.post("/ingest", dependencies=[Depends(_verify_token)])
async def ingest_darkpool(payload: dict = Body(...),
                          session: AsyncSession = Depends(get_session)):
    if not isinstance(payload.get("items"), list):
        return {"status": "error", "detail": "payload musí obsahovat pole 'items'"}
    payload.setdefault("generated", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    text = json.dumps(payload, ensure_ascii=False)
    row = await session.scalar(
        select(DarkPoolSnapshot).where(DarkPoolSnapshot.name == _SNAPSHOT_NAME)
    )
    if row:
        row.payload = text
    else:
        session.add(DarkPoolSnapshot(name=_SNAPSHOT_NAME, payload=text))
    await session.commit()
    log.info("Dark Pool snapshot uložen", items=len(payload["items"]), week=payload.get("week"))
    return {"status": "ok", "items": len(payload["items"])}
