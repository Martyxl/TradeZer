"""Právní náležitosti: souhlas při registraci, export dat (GDPR čl. 20), smazání účtu (čl. 17),
informace o odstoupení v Stripe Checkout."""
import os
import pytest

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["ANTHROPIC_API_KEY"] = "test-key"
os.environ["INTERNAL_API_TOKEN"] = "test-token"

from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, func
from app.main import app
from app.db.base import Base
from app.db.engine import engine
from app.db.session import session_context
from app.legal import TERMS_VERSION, CHECKOUT_SUBMIT_MESSAGE
from app.models import User, InvestmentTx
from app.models.journal import JournalEntry
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
async def test_registration_requires_terms_and_stores_consent():
    async with _client() as c:
        body = {"email": "a@example.com", "password": "secret123"}
        r = await c.post("/api/auth/register", json=body)
        assert r.status_code == 400 and "souhlas" in r.json()["detail"].lower()
        # řetězec "true" ani false nestačí — musí být skutečné true
        for bad in ("true", False, 1, None):
            assert (await c.post("/api/auth/register", json={**body, "accept_terms": bad})).status_code == 400
        assert (await c.post("/api/auth/register", json={**body, "accept_terms": True})).status_code == 200
    async with session_context() as s:
        u = await s.scalar(select(User).where(User.email == "a@example.com"))
        assert u.terms_version == TERMS_VERSION and u.terms_accepted_at is not None


@pytest.mark.asyncio
async def test_export_contains_own_data_only_and_no_secrets():
    async with _client() as c:
        h = await auth_headers(c, "me@example.com")
        other = await auth_headers(c, "other@example.com")
        await c.post("/api/journal", json={"instrument": "NQ", "direction": "long"}, headers=h)
        await c.post("/api/journal", json={"instrument": "GOLD", "direction": "short"}, headers=other)
        await c.post("/api/investments", json={"tx_type": "buy", "symbol": "AAPL", "quantity": 1, "price": 100, "currency": "USD"}, headers=h)
        assert (await c.get("/api/auth/export")).status_code == 401
        r = await c.get("/api/auth/export", headers=h)
        assert r.status_code == 200
        assert "attachment" in r.headers["content-disposition"] and r.headers["cache-control"] == "no-store"
        d = r.json()
        assert d["account"]["email"] == "me@example.com" and d["account"]["terms_version"] == TERMS_VERSION
        assert [e["instrument"] for e in d["journal_entries"]] == ["NQ"]            # cizí záznam NE
        assert [t["symbol"] for t in d["investment_transactions"]] == ["AAPL"]
        assert "password" not in r.text.lower()                                      # žádný hash hesla


@pytest.mark.asyncio
async def test_delete_account_removes_everything_and_requires_password():
    async with _client() as c:
        h = await auth_headers(c, "bye@example.com")
        keep = await auth_headers(c, "stay@example.com")
        await c.post("/api/journal", json={"instrument": "NQ", "direction": "long"}, headers=h)
        await c.post("/api/journal", json={"instrument": "ES", "direction": "long"}, headers=keep)
        await c.post("/api/investments", json={"tx_type": "buy", "symbol": "MSFT", "quantity": 1, "price": 1, "currency": "USD"}, headers=h)
        assert (await c.post("/api/auth/delete-account", json={"password": "secret123"})).status_code == 401
        assert (await c.post("/api/auth/delete-account", json={"password": "wrong"}, headers=h)).status_code == 400
        r = await c.post("/api/auth/delete-account", json={"password": "secret123"}, headers=h)
        assert r.status_code == 200 and r.json()["status"] == "deleted"
        assert (await c.get("/api/auth/me", headers=h)).status_code == 401           # účet je pryč
        assert (await c.post("/api/auth/login", json={"email": "bye@example.com", "password": "secret123"})).status_code in (400, 401)
        # cizí data zůstala
        assert len((await c.get("/api/journal", headers=keep)).json()["entries"]) == 1
    async with session_context() as s:
        assert await s.scalar(select(func.count()).select_from(JournalEntry)) == 1
        assert await s.scalar(select(func.count()).select_from(InvestmentTx)) == 0


@pytest.mark.asyncio
async def test_admin_account_cannot_be_deleted_from_app():
    async with _client() as c:
        h = await auth_headers(c, "boss@example.com", admin=True)
        r = await c.post("/api/auth/delete-account", json={"password": "secret123"}, headers=h)
        assert r.status_code == 400


class _FakeStripe:
    def __init__(self, fail=False):
        self.fail, self.cancelled = fail, []
        self.Subscription = self

    def list(self, **kw):
        if self.fail:
            raise RuntimeError("stripe down")
        return {"data": [{"id": "sub_1", "status": "active"}, {"id": "sub_old", "status": "canceled"}]}

    def cancel(self, sid):
        self.cancelled.append(sid)


@pytest.mark.asyncio
async def test_delete_cancels_active_stripe_subscription(monkeypatch):
    fake = _FakeStripe()
    monkeypatch.setattr("app.routers.billing._require_stripe", lambda: fake)
    async with _client() as c:
        h = await auth_headers(c, "paid@example.com")
        async with session_context() as s:
            u = await s.scalar(select(User).where(User.email == "paid@example.com"))
            u.stripe_customer_id = "cus_123"
            await s.commit()
        r = await c.post("/api/auth/delete-account", json={"password": "secret123"}, headers=h)
        assert r.status_code == 200
    assert fake.cancelled == ["sub_1"]                                               # jen aktivní, ne zrušené


@pytest.mark.asyncio
async def test_delete_aborts_when_stripe_cancel_fails(monkeypatch):
    """Nikdy nesmazat účet, když by se dál strhávaly peníze za nezrušené předplatné."""
    monkeypatch.setattr("app.routers.billing._require_stripe", lambda: _FakeStripe(fail=True))
    async with _client() as c:
        h = await auth_headers(c, "stuck@example.com")
        async with session_context() as s:
            u = await s.scalar(select(User).where(User.email == "stuck@example.com"))
            u.stripe_customer_id = "cus_999"
            await s.commit()
        r = await c.post("/api/auth/delete-account", json={"password": "secret123"}, headers=h)
        assert r.status_code == 502
        assert (await c.get("/api/auth/me", headers=h)).status_code == 200           # účet zůstal


def test_checkout_message_informs_about_withdrawal_and_links_terms():
    m = CHECKOUT_SUBMIT_MESSAGE
    assert "obchodni-podminky" in m and "ochrana-osobnich-udaju" in m
    assert "okamžité zahájení" in m and "poměrnou část" in m
    assert len(m) < 1200                                                              # limit Stripe custom_text


@pytest.mark.asyncio
async def test_checkout_session_gets_legal_text(monkeypatch):
    """Do Stripe Checkout musí odejít text o souhlasu s VOP a okamžitém zahájení služby."""
    from app.config import settings
    settings.stripe_price_pro_month = "price_pro_m"
    captured = {}

    class FakeCheckout:
        class Session:
            @staticmethod
            def create(**params):
                captured.update(params)
                return {"url": "https://checkout.stripe.test/x"}

    class Fake:
        checkout = FakeCheckout
    monkeypatch.setattr("app.routers.billing._require_stripe", lambda: Fake())
    async with _client() as c:
        h = await auth_headers(c, "buyer@example.com")
        async with session_context() as s:
            u = await s.scalar(select(User).where(User.email == "buyer@example.com"))
            u.stripe_customer_id = "cus_buyer"
            await s.commit()
        r = await c.post("/api/billing/checkout", json={"tier": "pro", "interval": "month"}, headers=h)
        assert r.status_code == 200, r.text
    msg = captured["custom_text"]["submit"]["message"]
    assert msg == CHECKOUT_SUBMIT_MESSAGE and "okamžité zahájení" in msg
