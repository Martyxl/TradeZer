"""Ingest job — stáhne fundamenty přes MarketDataProvider a uloží do DB.

Pravidla (sekce 4 specu):
- Běží mimo request path (CLI `python -m app.valuation.ingest` nebo z token endpointu).
- Cache = val_raw_snapshots (append-only). Dnešní snapshot se znovu netahá ze sítě
  (pokud není force), stejná data se rebuildnou z payloadu.
- Idempotentní: opakovaný běh za stejný den nezaloží duplicity (unique constrainty).
- Sekvenčně, s prodlevou mezi tickery + exponenciální backoff. Jeden padlý ticker
  nesmí shodit celý běh.
- Chybí data → None, nikdy neimputovat.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import date, datetime, timedelta

import structlog
from sqlalchemy import select

from app.config import settings
from app.db.engine import engine
from app.db.base import Base
from app.db.session import session_context
from app.valuation.models import (
    ValInstrument, ValRawSnapshot, ValFinancials, ValEstimate,
    ValEstimateTrend, ValEarningsHistory, ValPriceDaily,
)
from app.valuation.providers import get_provider
from app.valuation.providers.base import (
    ProviderBundle, Profile, FinancialStatement, EstimatePoint,
    RevisionTrend, EarningsRow, PriceBar,
)
from app.valuation.universe import peer_universe, resolve_group

log = structlog.get_logger(__name__)

RATE_LIMIT_SECONDS = 1.5     # prodleva mezi tickery
PRICE_HISTORY_YEARS = 6      # ~5 let pro percentily + rezerva

_ENDPOINTS = ("profile", "financials", "estimates", "revisions", "earnings_history", "prices")


# ---- cache (val_raw_snapshots) ----------------------------------------------

async def _cached_bundle(session, ticker: str, source: str, today: date) -> ProviderBundle | None:
    """Rebuild bundle z dnešních raw snapshotů (cache hit), jinak None."""
    rows = (await session.execute(
        select(ValRawSnapshot).where(
            ValRawSnapshot.ticker == ticker,
            ValRawSnapshot.source == source,
            ValRawSnapshot.as_of_date == today,
        )
    )).scalars().all()
    have = {r.endpoint: r.payload for r in rows}
    if not all(ep in have for ep in _ENDPOINTS):
        return None
    prof = have["profile"]
    return ProviderBundle(
        ticker=ticker,
        profile=Profile(**prof) if prof else None,
        financials=[FinancialStatement(**r) for r in have["financials"]],
        estimates=[EstimatePoint(**r) for r in have["estimates"]],
        revisions=[RevisionTrend(**r) for r in have["revisions"]],
        earnings_history=[EarningsRow(**r) for r in have["earnings_history"]],
        prices=[PriceBar(**r) for r in have["prices"]],
    )


async def _store_raw(session, ticker: str, source: str, today: date, bundle: ProviderBundle) -> None:
    """Uloží každou sekci jako append-only snapshot (idempotentně)."""
    payloads = {
        "profile": asdict(bundle.profile) if bundle.profile else {},
        "financials": [asdict(x) for x in bundle.financials],
        "estimates": [asdict(x) for x in bundle.estimates],
        "revisions": [asdict(x) for x in bundle.revisions],
        "earnings_history": [asdict(x) for x in bundle.earnings_history],
        "prices": [asdict(x) for x in bundle.prices],
    }
    for endpoint, payload in payloads.items():
        exists = await session.scalar(select(ValRawSnapshot.id).where(
            ValRawSnapshot.ticker == ticker, ValRawSnapshot.source == source,
            ValRawSnapshot.endpoint == endpoint, ValRawSnapshot.as_of_date == today,
        ))
        if exists:
            continue
        session.add(ValRawSnapshot(
            ticker=ticker, source=source, endpoint=endpoint,
            as_of_date=today, payload=payload,
        ))


# ---- normalizace do typovaných tabulek --------------------------------------

def _parse_date(s: str | None):
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


async def _upsert_financials(session, ticker: str, source: str, stmts: list[FinancialStatement]) -> None:
    for s in stmts:
        pe = _parse_date(s.period_end)
        if pe is None:
            continue
        existing = (await session.execute(select(ValFinancials).where(
            ValFinancials.ticker == ticker, ValFinancials.period_end == pe,
            ValFinancials.period_type == s.period_type,
        ).order_by(ValFinancials.revision_no.desc()))).scalars().first()
        vals = dict(
            revenue=s.revenue, gross_profit=s.gross_profit, operating_income=s.operating_income,
            ebitda=s.ebitda, net_income=s.net_income, eps_diluted=s.eps_diluted,
            shares_diluted=s.shares_diluted, cfo=s.cfo, capex=s.capex,
            total_debt=s.total_debt, cash_and_equivalents=s.cash_and_equivalents,
            total_equity=s.total_equity,
        )
        if existing:
            # Revize = nový řádek jen když se čísla reálně změnila
            changed = any(getattr(existing, k) != v for k, v in vals.items())
            if not changed:
                continue
            revision_no = existing.revision_no + 1
        else:
            revision_no = 0
        session.add(ValFinancials(
            ticker=ticker, period_end=pe, period_type=s.period_type,
            report_date=_parse_date(s.report_date), source=source,
            revision_no=revision_no, **vals,
        ))


async def _upsert_by_key(session, model, key_filter, factory) -> None:
    exists = await session.scalar(select(model.id).where(*key_filter))
    if not exists:
        session.add(factory())


async def _normalize(session, ticker: str, source: str, bundle: ProviderBundle) -> None:
    # Profil → val_instruments (skupina z GICS + override)
    if bundle.profile:
        inst = await session.scalar(select(ValInstrument).where(ValInstrument.ticker == ticker))
        if inst:
            p = bundle.profile
            inst.name = p.name or inst.name
            inst.exchange = p.exchange or inst.exchange
            inst.currency = p.currency or inst.currency
            inst.gics_sector = p.gics_sector or inst.gics_sector
            inst.gics_industry = p.gics_industry or inst.gics_industry
            grp = resolve_group(ticker, p.gics_sector, p.gics_industry)
            if grp:
                inst.group_key = grp

    await _upsert_financials(session, ticker, source, bundle.financials)

    for e in bundle.estimates:
        aod = _parse_date(e.as_of_date)
        if aod is None:
            continue
        await _upsert_by_key(
            session, ValEstimate,
            (ValEstimate.ticker == ticker, ValEstimate.as_of_date == aod,
             ValEstimate.horizon == e.horizon, ValEstimate.metric == e.metric),
            lambda e=e, aod=aod: ValEstimate(
                ticker=ticker, as_of_date=aod, horizon=e.horizon, metric=e.metric,
                avg=e.avg, low=e.low, high=e.high, n_analysts=e.n_analysts,
                year_ago_value=e.year_ago_value, source=source),
        )

    for r in bundle.revisions:
        aod = _parse_date(r.as_of_date)
        if aod is None:
            continue
        await _upsert_by_key(
            session, ValEstimateTrend,
            (ValEstimateTrend.ticker == ticker, ValEstimateTrend.as_of_date == aod,
             ValEstimateTrend.horizon == r.horizon),
            lambda r=r, aod=aod: ValEstimateTrend(
                ticker=ticker, as_of_date=aod, horizon=r.horizon, current=r.current,
                days_ago_7=r.days_ago_7, days_ago_30=r.days_ago_30, days_ago_60=r.days_ago_60,
                days_ago_90=r.days_ago_90, up_last_30d=r.up_last_30d, down_last_30d=r.down_last_30d),
        )

    for h in bundle.earnings_history:
        pe = _parse_date(h.period_end)
        if pe is None:
            continue
        await _upsert_by_key(
            session, ValEarningsHistory,
            (ValEarningsHistory.ticker == ticker, ValEarningsHistory.period_end == pe),
            lambda h=h, pe=pe: ValEarningsHistory(
                ticker=ticker, period_end=pe, report_date=_parse_date(h.report_date),
                eps_actual=h.eps_actual, eps_estimate=h.eps_estimate, surprise_pct=h.surprise_pct),
        )

    # Ceny: dávkově (per-row SELECT+INSERT je proti vzdálenému Postgresu neúnosné —
    # ~1500 barů/ticker × 2 round-tripy = tisíce dotazů po síti). Jeden SELECT
    # existujících dat + jeden hromadný insert chybějících.
    existing_dates = set(await session.scalars(
        select(ValPriceDaily.date).where(ValPriceDaily.ticker == ticker)))
    new_rows = []
    seen = set()
    for b in bundle.prices:
        d = _parse_date(b.date)
        if d is None or d in existing_dates or d in seen:
            continue
        seen.add(d)
        new_rows.append(ValPriceDaily(
            ticker=ticker, date=d, open=b.open, high=b.high, low=b.low,
            close=b.close, adj_close=b.adj_close, volume=b.volume))
    if new_rows:
        session.add_all(new_rows)


# ---- orchestrace ------------------------------------------------------------

async def ingest_ticker(session, provider, ticker: str, today: date, force: bool) -> str:
    """Vrátí 'cache' | 'fetched' | 'fail'."""
    source = provider.name
    bundle = None if force else await _cached_bundle(session, ticker, source, today)
    result = "cache"
    if bundle is None:
        price_start = today - timedelta(days=365 * PRICE_HISTORY_YEARS)
        last_exc = None
        for attempt in range(3):
            try:
                bundle = await asyncio.to_thread(provider.fetch_bundle, ticker, price_start, today)
                break
            except Exception as e:  # noqa: BLE001
                last_exc = e
                await asyncio.sleep(2 ** attempt)
        if bundle is None:
            log.warning("Ingest fetch failed", ticker=ticker, error=str(last_exc))
            return "fail"
        await _store_raw(session, ticker, source, today, bundle)
        result = "fetched"

    await _normalize(session, ticker, source, bundle)
    await session.commit()
    return result


async def ingest_all(session, tickers: list[str] | None = None, force: bool = False) -> dict:
    provider = get_provider()
    tickers = tickers or peer_universe()
    today = datetime.utcnow().date()
    stats = {"total": len(tickers), "fetched": 0, "cache": 0, "failed": 0, "provider": provider.name}

    for i, ticker in enumerate(tickers):
        try:
            r = await ingest_ticker(session, provider, ticker, today, force)
            stats["fetched" if r == "fetched" else "cache" if r == "cache" else "failed"] += 1
        except Exception as e:  # noqa: BLE001
            await session.rollback()
            stats["failed"] += 1
            log.error("Ingest ticker error", ticker=ticker, error=str(e))
        if provider.name != "fixture" and i < len(tickers) - 1:
            await asyncio.sleep(RATE_LIMIT_SECONDS)

    log.info("Ingest complete", **stats)
    return stats


async def _main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_context() as session:
        stats = await ingest_all(session)
    print(f"Ingest [{stats['provider']}]: {stats['fetched']} staženo, {stats['cache']} z cache, "
          f"{stats['failed']} chyb z {stats['total']}")


if __name__ == "__main__":
    asyncio.run(_main())
