"""Testy Stripe billing wiringu — bez reálného Stripe klíče.

Ověřuje: /config tvar + bezpečnou degradaci (bez klíče → 503), a že checkout/portal
vyžadují přihlášení (401). Reálné Stripe volání se netestují (hostovaný Checkout).
"""
import os
import pytest

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["ANTHROPIC_API_KEY"] = "test-key"
os.environ["INTERNAL_API_TOKEN"] = "test-token"
# Žádný STRIPE_SECRET_KEY → endpoints musí bezpečně vracet 503, ne spadnout.
os.environ.pop("STRIPE_SECRET_KEY", None)

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
async def test_config_public_no_key():
    async with _client() as c:
        r = await c.get("/api/billing/config")
    assert r.status_code == 200
    d = r.json()
    assert d["enabled"] is False          # bez klíče vypnuto
    assert d["publishable_key"] == ""
    assert d["buyable"] == {}             # žádný price nastavený


@pytest.mark.asyncio
async def test_checkout_requires_auth():
    async with _client() as c:
        r = await c.post("/api/billing/checkout", json={"tier": "pro", "interval": "month"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_portal_requires_auth():
    async with _client() as c:
        r = await c.post("/api/billing/portal", json={})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_checkout_503_when_unconfigured():
    async with _client() as c:
        h = await auth_headers(c, "billing1@example.com")
        r = await c.post("/api/billing/checkout", json={"tier": "pro", "interval": "month"}, headers=h)
    assert r.status_code == 503  # přihlášen, ale Stripe není nakonfigurovaný


@pytest.mark.asyncio
async def test_webhook_503_when_unconfigured():
    async with _client() as c:
        r = await c.post("/api/billing/webhook", content=b"{}",
                         headers={"stripe-signature": "x"})
    assert r.status_code == 503
