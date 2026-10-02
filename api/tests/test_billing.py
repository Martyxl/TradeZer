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
# Namapuj jeden price na tier pro test webhook logiky (_apply_subscription).
os.environ["STRIPE_PRICE_PRO_MONTH"] = "price_test_pro_m"

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


@pytest.mark.asyncio
async def test_apply_subscription_sets_plan():
    """Regrese: webhook logika musí umět plain dict (ne StripeObject) a novou API
    verzi (current_period_end v items) a nastavit plan dle price→tier."""
    from app.routers.billing import _apply_subscription
    from app.config import settings
    from app.models import User
    from app.db.session import session_context

    settings.stripe_price_pro_month = "price_test_pro_m"  # price → tier mapa za běhu

    # Uživatel s navázaným Stripe zákazníkem (jako po /checkout).
    async with session_context() as s:
        u = User(email="sub@example.com", password_hash="x", plan="free",
                 stripe_customer_id="cus_test1")
        s.add(u)
        await s.commit()
        uid = u.id

    sub = {
        "status": "active",
        "items": {"data": [{"price": {"id": "price_test_pro_m"},
                            "current_period_end": 1800000000}]},
    }
    await _apply_subscription(None, "cus_test1", sub)

    async with session_context() as s:
        u = await s.get(User, uid)
        assert u.plan == "pro"
        assert u.subscription_status == "active"
        assert u.subscription_period_end is not None


@pytest.mark.asyncio
async def test_apply_subscription_canceled_downgrades():
    from app.routers.billing import _apply_subscription
    from app.models import User
    from app.db.session import session_context

    async with session_context() as s:
        u = User(email="sub2@example.com", password_hash="x", plan="pro",
                 stripe_customer_id="cus_test2")
        s.add(u)
        await s.commit()
        uid = u.id

    await _apply_subscription(None, "cus_test2", {"status": "canceled", "items": {"data": []}})

    async with session_context() as s:
        u = await s.get(User, uid)
        assert u.plan == "free"
