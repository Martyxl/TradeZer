"""Režim „vše zdarma“ (FREE_ACCESS): přihlášený uživatel má vše do úrovně Pro, anonym nic,
Elite zůstává zamčený (nemáme data), nákup je vypnutý."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.db.base import Base
from app.db.engine import engine
from app.main import app
from tests._auth import auth_headers

CASES = ["/api/valuation/overview", "/api/discovery", "/api/smart-money"]


@pytest.fixture(autouse=True)
async def setup_db(monkeypatch):
    monkeypatch.setattr(settings, "free_access", True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_free_user_gets_everything_up_to_pro():
    async with _client() as c:
        h = await auth_headers(c, "free@t.cz", plan="free")
        for u in CASES:
            assert (await c.get(u, headers=h)).status_code == 200, u


@pytest.mark.asyncio
async def test_anonymous_still_needs_account():
    async with _client() as c:
        for u in CASES:
            assert (await c.get(u)).status_code == 401, u


@pytest.mark.asyncio
async def test_elite_stays_locked_and_nothing_is_for_sale():
    async with _client() as c:
        h = await auth_headers(c, "free2@t.cz", plan="free")
        assert (await c.get("/api/valuation/AAPL/analysts", headers=h)).status_code == 403
        cfg = (await c.get("/api/billing/config")).json()
        assert cfg["free_access"] is True and cfg["enabled"] is False and cfg["buyable"] == {}
        r = await c.post("/api/billing/checkout", json={"tier": "pro", "interval": "month"}, headers=h)
        assert r.status_code == 400 and "zdarma" in r.json()["detail"]


def test_entitled_helper():
    from types import SimpleNamespace as U
    from app.routers.auth import entitled
    free = U(is_admin=False, plan="free")
    assert entitled(free, "trader") and entitled(free, "pro") and not entitled(free, "elite")
    assert entitled(U(is_admin=True, plan="free"), "elite")
