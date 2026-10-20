"""Spark úlohy (calibrate / outlook_eval) běží nad prázdnou DB bez chyby."""
import os
import pytest

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["ANTHROPIC_API_KEY"] = "test-key"

from app.db.base import Base
from app.db.engine import engine
from app import spark_jobs as jobs


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_calibrate_on_empty_db():
    r = await jobs.run_calibrate()
    assert r == {"checked": 0, "recorded": 0, "failed": 0, "skipped": 0, "unresolvable": 0}


@pytest.mark.asyncio
async def test_outlook_eval_on_empty_db(monkeypatch):
    async def no_events(*a, **k):
        return []
    monkeypatch.setattr("app.sources.forex_factory.get_upcoming_events", no_events)
    monkeypatch.setattr("app.services.outlook_service.get_upcoming_events", no_events)
    r = await jobs.run_outlook_eval()
    assert r.get("created") == 0


@pytest.mark.asyncio
async def test_once_swallows_errors(monkeypatch, capsys):
    async def boom():
        raise RuntimeError("db down")
    monkeypatch.setitem(jobs.JOBS, "calibrate", boom)
    assert await jobs._once("calibrate") is False
    assert "CHYBA" in capsys.readouterr().out
