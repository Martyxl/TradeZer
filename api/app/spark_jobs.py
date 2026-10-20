"""Periodické úlohy mimo Vercel — běží na Sparku přímo nad produkční DB (stejný kód jako API endpointy).

  python -m app.spark_jobs calibrate     → CalibrationService.run()   (ex POST /api/calibrate)
  python -m app.spark_jobs outlook_eval  → evaluate_outlook()         (ex POST /api/bias/outlook/evaluate)
  přepínač --loop MINUT            → opakuj po N minutách (chyba jednoho běhu smyčku neshodí)

Proč: kalibrace stahuje ceny z Yahoo (z domácí IP funguje, z cloudu bývá blokované) a na Vercelu
běžela na limitu 60 s každých 30 min = zbytečně placené Active CPU. Potřebuje jen DATABASE_URL.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

import structlog

from app.db import session_context

log = structlog.get_logger(__name__)


async def run_calibrate() -> dict:
    from app.services.calibration_service import CalibrationService
    async with session_context() as session:
        return await CalibrationService(session).run()


async def run_outlook_eval() -> dict:
    from app.services.outlook_service import evaluate_outlook
    async with session_context() as session:
        return await evaluate_outlook(session)


JOBS = {"calibrate": run_calibrate, "outlook_eval": run_outlook_eval}


async def _once(name: str) -> bool:
    t0 = time.time()
    try:
        result = await JOBS[name]()
        print(f"{name} ok za {time.time() - t0:.1f}s: {json.dumps(result, default=str)[:300]}", flush=True)
        return True
    except Exception as e:  # noqa: BLE001 — smyčka musí přežít výpadek DB/Yahoo
        print(f"{name} CHYBA: {e!r}", flush=True)
        return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("job", choices=sorted(JOBS))
    ap.add_argument("--loop", type=int, default=0, help="opakuj po N minutách (0 = jednou)")
    a = ap.parse_args()
    if not a.loop:
        sys.exit(0 if asyncio.run(_once(a.job)) else 1)
    while True:
        asyncio.run(_once(a.job))
        time.sleep(a.loop * 60)


if __name__ == "__main__":
    main()
