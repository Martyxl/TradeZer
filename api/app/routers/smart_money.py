"""Smart Money — insider (SEC Form 4) + congress aktivita.

GET  /api/smart-money         → poslední snapshot (veřejné čtení)
POST /api/smart-money/ingest  → uloží nový snapshot (token; volá `data/smart_money_scan.py --push`)
GET  /api/smart-money/funds   → fondy: 13F pozice a změny + 13D/13G podíly (`data/fund_holdings_scan.py`)
POST /api/smart-money/funds/ingest

Snapshot je 1 JSON blob v DB (SmartMoneySnapshot name="latest").
"""
import json
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Body, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import SmartMoneySnapshot
from app.routers.admin import _verify_token
from app.routers.auth import require_plan

router = APIRouter(prefix="/api/smart-money", tags=["smart-money"])
log = structlog.get_logger(__name__)

_SNAPSHOT_NAME = "latest"
_EMPTY = {"generated": None, "count": 0, "buys": 0, "sells": 0,
          "top_buys": [], "insiders": [], "congress": [],
          "note": "Zatím žádný snapshot. Spusť data/smart_money_scan.py --push."}


@router.get("", dependencies=[Depends(require_plan("pro"))])
async def get_smart_money(session: AsyncSession = Depends(get_session)):
    """Poslední snapshot insider/congress aktivity (nikdy nespadne)."""
    row = await session.scalar(
        select(SmartMoneySnapshot).where(SmartMoneySnapshot.name == _SNAPSHOT_NAME)
    )
    if not row:
        return _EMPTY
    try:
        return json.loads(row.payload)
    except (ValueError, TypeError):
        return {**_EMPTY, "note": "Poškozený snapshot."}


@router.post("/ingest", dependencies=[Depends(_verify_token)])
async def ingest_smart_money(
    payload: dict = Body(...),
    session: AsyncSession = Depends(get_session),
):
    """Uloží/přepíše poslední snapshot. Payload = výstup smart_money_scan (dict s `insiders`)."""
    if not isinstance(payload.get("insiders"), list):
        return {"status": "error", "detail": "payload musí obsahovat pole 'insiders'"}
    payload.setdefault("generated", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    text = json.dumps(payload, ensure_ascii=False)

    row = await session.scalar(
        select(SmartMoneySnapshot).where(SmartMoneySnapshot.name == _SNAPSHOT_NAME)
    )
    if row:
        row.payload = text
    else:
        session.add(SmartMoneySnapshot(name=_SNAPSHOT_NAME, payload=text))
    await session.commit()
    log.info("Smart Money snapshot uložen", insiders=len(payload["insiders"]))
    return {"status": "ok", "insiders": len(payload["insiders"])}


_FUNDS_NAME = "funds"
_FUNDS_EMPTY = {"generated": None, "quarter": None, "funds": [], "consensus_buys": [], "consensus_sells": [],
                "most_held": [], "stakes": [], "by_ticker": {}, "fund_names": {},
                "note": "Zatím žádná data fondů. Spusť data/fund_holdings_scan.py --push."}


@router.get("/funds", dependencies=[Depends(require_plan("pro"))])
async def get_funds(session: AsyncSession = Depends(get_session)):
    """Co drží, kupují a prodávají vybrané fondy (13F) + nové podíly nad 5 % (13D/13G)."""
    row = await session.scalar(select(SmartMoneySnapshot).where(SmartMoneySnapshot.name == _FUNDS_NAME))
    if not row:
        return _FUNDS_EMPTY
    try:
        return json.loads(row.payload)
    except (ValueError, TypeError):
        return {**_FUNDS_EMPTY, "note": "Poškozený snapshot."}


@router.post("/funds/ingest", dependencies=[Depends(_verify_token)])
async def ingest_funds(payload: dict = Body(...), session: AsyncSession = Depends(get_session)):
    if not isinstance(payload.get("funds"), list) or not payload["funds"]:
        return {"status": "error", "detail": "payload musí obsahovat neprázdné pole 'funds'"}
    payload.setdefault("generated", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    text = json.dumps(payload, ensure_ascii=False)
    row = await session.scalar(select(SmartMoneySnapshot).where(SmartMoneySnapshot.name == _FUNDS_NAME))
    if row:
        row.payload = text
    else:
        session.add(SmartMoneySnapshot(name=_FUNDS_NAME, payload=text))
    await session.commit()
    log.info("Smart Money fondy uloženy", funds=len(payload["funds"]), bytes=len(text))
    return {"status": "ok", "funds": len(payload["funds"]), "stakes": len(payload.get("stakes") or [])}
