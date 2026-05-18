"""APScheduler jobs — periodický refresh a denní summary."""
import asyncio
from datetime import date, datetime

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.db.session import session_context
from app.services.calibration_service import CalibrationService
from app.services.news_aggregator import NewsAggregator
from app.services.summary_service import SummaryService

log = structlog.get_logger(__name__)

scheduler = AsyncIOScheduler()


async def _refresh_job():
    log.info("Scheduler: refresh job start")
    async with session_context() as session:
        aggregator = NewsAggregator(session)
        stats = await aggregator.refresh()
    log.info("Scheduler: refresh job done", **stats)


async def _calibration_job():
    log.info("Scheduler: calibration job start")
    async with session_context() as session:
        service = CalibrationService(session)
        stats = await service.run()
    log.info("Scheduler: calibration job done", **stats)


async def _daily_summary_job():
    log.info("Scheduler: daily summary job start")
    async with session_context() as session:
        service = SummaryService(session)
        await service.generate_all(date.today())
    log.info("Scheduler: daily summary job done")


def start_scheduler() -> None:
    scheduler.add_job(
        _refresh_job,
        trigger=IntervalTrigger(minutes=settings.refresh_interval_minutes),
        id="refresh",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        _calibration_job,
        trigger=IntervalTrigger(minutes=15),
        id="calibration",
        replace_existing=True,
        coalesce=True,
    )
    scheduler.add_job(
        _daily_summary_job,
        trigger=CronTrigger(hour=23, minute=0),
        id="daily_summary",
        replace_existing=True,
    )
    scheduler.start()
    log.info(
        "Scheduler started",
        refresh_interval_minutes=settings.refresh_interval_minutes,
    )


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
