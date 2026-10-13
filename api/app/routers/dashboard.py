"""Agregovaný endpoint dashboardu — JEDEN požadavek místo ~11.

Dashboard dřív při načtení volal ~11 endpointů (tickers, news, summary, bias ×4, gamma ×2, regime,
events). Při studeném startu každé volání probudilo vlastní instanci funkce a vlastní DB spojení
(→ až 16 s). Tady se vše vyřeší v jedné funkci, jedné DB session, a výsledek se jako celek
cachuje na CDN (`/api/dashboard` je v _CACHEABLE_PREFIXES, s-maxage=60 + stale-while-revalidate).

Tvar každé části je IDENTICKÝ s původním endpointem (frontend jen přesměruje stávající volání
přes `dashFetch`, viz web/lib/dashboardData.ts). Každá část je izolovaná: selhání jedné nezboří
ostatní (část = null + záznam v `errors`) a 404 (např. chybějící denní summary) = null.
Outlook (LLM narativ, pomalý) sem záměrně NEPATŘÍ — načítá si ho karta sama pod ohybem.
"""
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas import DailySummaryOut, TickerOut

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
log = structlog.get_logger(__name__)


@router.get("")
async def dashboard(
    ticker: str = Query(default="NQ"),
    session: AsyncSession = Depends(get_session),
):
    # Lazy importy handlerů (vyhne se kruhovým importům a nezdržuje start funkce)
    from app.routers import bias as r_bias
    from app.routers import gamma as r_gamma
    from app.routers import news as r_news
    from app.routers import regime as r_regime
    from app.routers import summary as r_summary
    from app.routers import tickers as r_tickers

    ticker = ticker.upper()[:20]
    errors: list[str] = []

    async def part(name: str, call):
        try:
            return jsonable_encoder(await call())
        except HTTPException as e:
            if e.status_code != 404:
                errors.append(f"{name}: HTTP {e.status_code}")
            return None  # 404 = „data neexistují“ (např. dnes ještě není denní summary)
        except Exception as e:  # noqa: BLE001 — část nesmí shodit celý dashboard
            log.warning("dashboard part failed", part=name, error=str(e))
            errors.append(f"{name}: {type(e).__name__}")
            try:
                await session.rollback()  # po chybě v DB musí být session zase použitelná
            except Exception:  # noqa: BLE001
                pass
            return None

    async def tickers():
        items = await r_tickers.list_tickers(session)
        return TypeAdapter(list[TickerOut]).validate_python(items, from_attributes=True)

    async def summary():
        item = await r_summary.get_daily_summary(ticker=ticker, date_filter=None, session=session)
        return DailySummaryOut.model_validate(item, from_attributes=True)

    async def gamma():
        data = await r_gamma._load(session)
        inst = (data.get("instruments") or {}).get(ticker)
        return {"generated": data.get("generated"), "ticker": ticker,
                "instrument": inst, "note": data.get("note")}

    out = {
        "ticker": ticker,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tickers": await part("tickers", tickers),
        "news": await part("news", lambda: r_news.list_news(
            ticker=ticker, date_filter=None, limit=25, offset=0, session=session)),
        "summary": await part("summary", summary),
        "bias_today": await part("bias_today", lambda: r_bias.bias_today(ticker=ticker, session=session)),
        "bias_stats_30": await part("bias_stats_30", lambda: r_bias.bias_stats(ticker=ticker, days=30, session=session)),
        "bias_stats_90": await part("bias_stats_90", lambda: r_bias.bias_stats(ticker=ticker, days=90, session=session)),
        "gamma": await part("gamma", gamma),
        "regime": await part("regime", lambda: r_regime.get_regime(session=session)),
        "events_today": await part("events_today", lambda: r_news.events_today(date_filter=None, session=session)),
    }
    out["errors"] = errors
    return out
