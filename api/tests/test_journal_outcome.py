"""Deník: SL/TP + přepínač Win/Loss přes API (vytvoření, dopočet exit/R, statistika)."""
import os
import pytest

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["ANTHROPIC_API_KEY"] = "test-key"
os.environ["INTERNAL_API_TOKEN"] = "test-token"

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.base import Base
from app.db.engine import engine
from tests._auth import auth_headers


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_sl_tp_outcome_roundtrip_and_stats():
    async with _client() as c:
        h = await auth_headers(c, "jr@example.com")
        base = {"instrument": "NQ", "direction": "short", "entry_price": 100,
                "stop_price": 105, "target_price": 90}
        loss = (await c.post("/api/journal", json={**base, "outcome": "loss"}, headers=h)).json()["entry"]
        assert loss["outcome"] == "loss" and loss["exit_price"] == 105 and loss["r_result"] == -1.0
        assert loss["stop_price"] == 105 and loss["target_price"] == 90
        win = (await c.post("/api/journal", json={**base, "outcome": "win"}, headers=h)).json()["entry"]
        assert win["exit_price"] == 90 and win["r_result"] == 2.0
        # výsledek bez R (jen přepínač, bez SL/TP) se počítá do win-rate
        await c.post("/api/journal", json={"instrument": "NQ", "direction": "long", "outcome": "win"}, headers=h)
        # neplatný výsledek se ignoruje
        bad = (await c.post("/api/journal", json={**base, "outcome": "foo"}, headers=h)).json()["entry"]
        assert bad["outcome"] is None and bad["r_result"] is None
        t = (await c.get("/api/journal/stats", headers=h)).json()["totals"]
        assert t["wins"] == 2 and t["losses"] == 1 and t["decided"] == 3
        # úprava: přepnutí na loss s ručně zadaným R zůstane
        upd = (await c.patch(f"/api/journal/{win['id']}",
                             json={"outcome": "loss", "r_result": -1, "exit_price": 105}, headers=h)).json()["entry"]
        assert upd["outcome"] == "loss" and upd["r_result"] == -1.0
