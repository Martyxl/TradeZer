"""Denní plán pro MT5 robota (Expert Advisor) — jednoduchý text „klíč=hodnota“ (MQL5 parsuje JSON špatně).

GET /api/ea/plan?ticker=NQ →
    ticker=NQ
    date=2026-10-23            obchodní den (UTC, den začíná 22:00)
    direction=up|down|neutral|unknown|none   (none = snapshot po London open ještě není)
    trust=62.0
    offset_pct=0.25            limit proti biasu po NY open (stejně jako karta Entry na dashboardu)
    ny_open_utc=13:30
    close_utc=21:00
    news_ok=1                  0 = kalendář nedostupný → robot má ten den raději neobchodovat
    news=2026-10-23T14:00:00Z|USD|ISM Manufacturing PMI   (high-impact zprávy dnešního dne, víc řádků)

Veřejné (bias je veřejný i na dashboardu). Bez CDN cache — robot potřebuje čerstvý stav.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import DailyBias, Ticker
from app.services import bias_service
from app.sources import forex_factory

router = APIRouter(prefix="/api/ea", tags=["ea"])

# Měny, jejichž zprávy hýbou daným instrumentem (FTMO: ±2 min kolem zpráv na symbolech s danou měnou).
NEWS_CCY = {"NQ": {"USD"}, "ES": {"USD"}, "YM": {"USD"}, "XAUUSD": {"USD"},
            "EURUSD": {"USD", "EUR"}, "GBPUSD": {"USD", "GBP"}, "USDJPY": {"USD", "JPY"}}


@router.get("/plan", response_class=PlainTextResponse)
async def ea_plan(ticker: str = Query(...), session: AsyncSession = Depends(get_session)) -> str:
    sym = ticker.upper()
    t = await session.scalar(select(Ticker).where(Ticker.symbol == sym))
    if t is None:
        raise HTTPException(status_code=404, detail="Neznámý ticker")
    tday = bias_service._trading_day(datetime.utcnow())
    snap = await session.scalar(select(DailyBias).where(DailyBias.ticker_id == t.id, DailyBias.bias_date == tday))
    direction = snap.direction if snap else "none"
    offset = bias_service._entry_offset(sym, direction, t.neutral_threshold) if direction in ("up", "down") else 0.0

    lines = [f"ticker={sym}", f"date={tday.isoformat()}", f"direction={direction}",
             f"trust={snap.trust_score if snap else 0}", f"offset_pct={offset}",
             f"ny_open_utc={bias_service.ny_open_utc(tday).strftime('%H:%M')}",
             f"close_utc={bias_service.ny_close_utc(tday).strftime('%H:%M')}"]
    try:
        events = await forex_factory.get_upcoming_events(window_before_min=1440, window_after_min=1440)
        news_ok = 1
    except Exception:  # noqa: BLE001
        events, news_ok = [], 0
    if news_ok and not events:
        # get_upcoming_events při chybě stahování vrací [] — prázdný týdenní kalendář je nepravděpodobný.
        news_ok = 1 if forex_factory._ff_cache.get("text") else 0
    ccys = NEWS_CCY.get(sym, {"USD"})
    today = tday.isoformat()
    lines.append(f"news_ok={news_ok}")
    for e in events:
        if e.get("impact") == "high" and e.get("currency") in ccys and (e.get("time_utc") or "")[:10] == today:
            title = (e.get("title") or "").replace("|", "/").replace("\n", " ")
            lines.append(f"news={e['time_utc']}|{e['currency']}|{title}")
    return "\n".join(lines) + "\n"
