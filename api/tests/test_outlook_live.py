"""Živá reakce na makro: výběr sledovaných eventů, výpočet pohybu ve workeru, ingest a výhled."""
import importlib.util
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["INTERNAL_API_TOKEN"] = "test-token"

from httpx import AsyncClient, ASGITransport  # noqa: E402
from app.main import app  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.engine import engine  # noqa: E402
from app.db.session import session_context  # noqa: E402
from app.models import Ticker  # noqa: E402
from app.services import outlook_service  # noqa: E402

_spec = importlib.util.spec_from_file_location("live_reaction", Path(__file__).parents[2] / "data" / "live_reaction.py")
worker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(worker)


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def test_due_events_window():
    now = datetime(2026, 11, 3, 13, 40, tzinfo=timezone.utc)
    ev = lambda t, title="CPI m/m", imp="high": {"title": title, "impact": imp, "currency": "USD",  # noqa: E731
                                                "time_utc": t.isoformat()}
    due = outlook_service.live_due_events([
        ev(now - timedelta(minutes=10)),                       # běží
        ev(now + timedelta(minutes=1), "ISM Services PMI"),    # za minutu → už sledovat
        ev(now - timedelta(minutes=70)),                       # po okně
        ev(now + timedelta(minutes=30)),                       # moc brzy
        ev(now - timedelta(minutes=5), "Něco jiného"),         # bez scénáře
        ev(now - timedelta(minutes=5), "CPI y/y", "low"),      # low impact
    ], now)
    assert [d["title"] for d in due] == ["CPI m/m", "ISM Services PMI"]


def test_worker_measure_points():
    ev = datetime(2026, 11, 3, 13, 30, tzinfo=timezone.utc)
    e = ev.timestamp()
    # cena 1.1000 před vydáním, pak každou minutu −1 pip
    bs = [(e + 60 * i, 1.1000 + (-0.0001 * (i + 1) if i >= 0 else 0)) for i in range(-10, 20)]
    m = worker.measure(bs, ev, ev + timedelta(minutes=16), proxy=False)
    assert m["p0"] == 1.1
    assert set(m["points"]) == {"1", "5", "15"}                 # 30/60 ještě neuplynulo
    assert m["points"]["5"] == pytest.approx(-0.04545, abs=1e-4)  # 5 pipů dolů
    assert m["last_pct"] < m["points"]["15"] <= m["points"]["5"]
    # trh zavřený (žádná cena před vydáním) → nic
    assert worker.measure([(e + 60, 1.1)], ev, ev + timedelta(minutes=5), proxy=False) is None


@pytest.mark.asyncio
async def test_ingest_and_outlook(monkeypatch):
    async with session_context() as s:
        s.add(Ticker(symbol="EURUSD", name="EUR/USD", asset_class="forex", source_symbol_map={}, neutral_threshold=0.0005))
        await s.commit()
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    ev_t = now - timedelta(minutes=20)
    title = "CPI m/m"

    async def fake_events(**kw):
        return [{"title": title, "impact": "high", "currency": "USD", "time_utc": ev_t.isoformat(),
                 "forecast": "0.3%", "previous": "0.2%", "actual": "0.5%"}]
    monkeypatch.setattr(outlook_service, "get_upcoming_events", fake_events)
    from app.config import settings
    monkeypatch.setattr(settings, "outlook_live_enabled", True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        item = {"event_title": title, "event_time_utc": ev_t.isoformat(), "ticker": "EURUSD", "p0": 1.1,
                "points": {"1": -0.02, "5": -0.11, "99": 5}, "last_pct": -0.15, "last_at": now.isoformat()}
        assert (await c.post("/api/bias/outlook/live/ingest", json={"items": [item]})).status_code in (401, 403)
        r = await c.post("/api/bias/outlook/live/ingest", json={"items": [item, {**item, "ticker": "AAPL"}]},
                         headers={"X-Internal-Token": "test-token"})
        assert r.json() == {"upserted": 1}
        item["points"]["15"] = -0.2
        await c.post("/api/bias/outlook/live/ingest", json={"items": [item]}, headers={"X-Internal-Token": "test-token"})
        async with session_context() as s:
            out = await outlook_service.build_outlook("EURUSD", s)
    live = out["scenarios"][0]["live"]
    assert live["points"] == {"1": -0.02, "5": -0.11, "15": -0.2}   # neznámý bod zahozen, upsert
    assert live["last_pct"] == -0.15 and live["thr_pct"] == 0.05 and live["proxy"] is None
    assert out["live_feature"] == "on"
    # bez licence (výchozí) se uložená data neukazují a web dostane signál pro zašedlou ukázku
    monkeypatch.setattr(settings, "outlook_live_enabled", False)
    async with session_context() as s:
        out = await outlook_service.build_outlook("EURUSD", s)
    assert out["scenarios"][0]["live"] is None and out["live_feature"] == "elite"
