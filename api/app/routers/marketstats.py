"""Market statistiky (Stats = Trader+, ORB = zdarma) servírované z DB.

PUT /api/marketstats/{kind}/{key}   → uloží blob (interní token; volá Spark `data/publish_stats.py`)
GET /api/marketstats/orb/{key}      → veřejné (výřez orb_sessions), CDN cache
GET /api/marketstats/stats/{key}    → plná statistika, jen plán Trader+ (server-side gate, bez CDN cache)

Cesta NENÍ pod /api/stats (ten prefix je v CDN cache → placená data by mohla skončit veřejně).
"""
import json
import re

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.stats_blob import MarketStatsBlob
from app.routers.admin import _verify_token
from app.routers.auth import require_plan

router = APIRouter(prefix="/api/marketstats", tags=["marketstats"])
log = structlog.get_logger(__name__)

KINDS = {"stats", "orb"}
_KEY_RE = re.compile(r"^[a-z0-9]{2,12}$")


def _name(kind: str, key: str) -> str:
    if kind not in KINDS or not _KEY_RE.match(key):
        raise HTTPException(status_code=404, detail="Neznámý druh nebo klíč")
    return f"{kind}:{key}"


async def _load(session: AsyncSession, kind: str, key: str) -> dict:
    row = await session.get(MarketStatsBlob, _name(kind, key))
    if row is None:
        raise HTTPException(status_code=404, detail="Statistika zatím není publikovaná")
    return json.loads(row.payload)


@router.put("/{kind}/{key}", dependencies=[Depends(_verify_token)])
async def publish(kind: str, key: str, payload: dict = Body(...),
                  session: AsyncSession = Depends(get_session)):
    name = _name(kind, key)
    if not isinstance(payload.get("meta"), dict):
        raise HTTPException(status_code=422, detail="Chybí meta")
    text = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    row = await session.get(MarketStatsBlob, name)
    if row:
        row.payload = text
    else:
        session.add(MarketStatsBlob(name=name, payload=text))
    await session.commit()
    log.info("Market stats publikovány", name=name, bytes=len(text))
    return {"status": "ok", "name": name, "bytes": len(text), "to": payload["meta"].get("to")}


@router.get("/orb/{key}")
async def get_orb(key: str, session: AsyncSession = Depends(get_session)):
    return await _load(session, "orb", key)


@router.get("/stats/{key}", dependencies=[Depends(require_plan("trader"))])
async def get_stats(key: str, session: AsyncSession = Depends(get_session)):
    return await _load(session, "stats", key)
