"""Seed val_groups a val_instruments (skupiny + univerza). Idempotentní upsert.

Spuštění: python -m app.db.seed_valuation
GICS sektor/skupina se u instrumentů doplní až při ingestu (P1) z profilu firmy;
zde zakládáme řádky s příslušností k display/peer univerzu.
"""
import asyncio

from sqlalchemy import select

from app.db.base import Base
from app.db.engine import engine
from app.db.session import session_context
from app.valuation.models import ValGroup, ValInstrument
from app.valuation.universe import GROUPS, GROUP_OVERRIDE, display_universe, peer_universe


async def seed_valuation(session) -> dict:
    stats = {"groups": 0, "instruments": 0}

    # Skupiny
    for g in GROUPS:
        existing = await session.scalar(select(ValGroup).where(ValGroup.key == g["key"]))
        if existing is None:
            session.add(ValGroup(**g))
            stats["groups"] += 1
        else:
            existing.label_cs = g["label_cs"]
            existing.label_en = g["label_en"]
            existing.color_hex = g["color_hex"]
            existing.sort_order = g["sort_order"]

    # Instrumenty
    display = set(display_universe())
    peers = peer_universe()
    for ticker in peers:
        existing = await session.scalar(select(ValInstrument).where(ValInstrument.ticker == ticker))
        # skupinu známe jen u override (semis) — zbytek doplní ingest z GICS
        group_key = GROUP_OVERRIDE.get(ticker)
        if existing is None:
            session.add(ValInstrument(
                ticker=ticker,
                group_key=group_key,
                in_display_universe=ticker in display,
                in_peer_universe=True,
                active=True,
            ))
            stats["instruments"] += 1
        else:
            existing.in_display_universe = ticker in display
            existing.in_peer_universe = True
            if group_key and not existing.group_key:
                existing.group_key = group_key

    await session.commit()
    return stats


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_context() as session:
        stats = await seed_valuation(session)
    print(f"Valuation seed: {stats['groups']} skupin, {stats['instruments']} instrumentů "
          f"({len(peer_universe())} v peer, {len(display_universe())} v display)")


if __name__ == "__main__":
    asyncio.run(main())
