"""Bezpečnostní testy server-side gate placených modulů — nejde obejít přímým API.

Matice: bez tokenu → 401, nedostatečný plán → 403, dostatečný plán/admin → 200.
Valuation = Trader+, Discovery a Smart Money = Pro+.
"""
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


# (endpoint, minimální plán) — plány, které MAJÍ projít, a které NE
CASES = [
    ("/api/valuation/overview", "trader"),
    ("/api/discovery", "pro"),
    ("/api/smart-money", "pro"),
]
RANK = {"free": 0, "trader": 1, "pro": 2, "elite": 3}


@pytest.mark.asyncio
@pytest.mark.parametrize("url,min_tier", CASES)
async def test_no_token_401(url, min_tier):
    async with _client() as c:
        r = await c.get(url)
    assert r.status_code == 401, f"{url}: {r.status_code}"


@pytest.mark.asyncio
@pytest.mark.parametrize("url,min_tier", CASES)
async def test_insufficient_plan_403(url, min_tier):
    # plán o stupeň nižší, než je potřeba → 403
    lower = [p for p, r in RANK.items() if r == RANK[min_tier] - 1][0]
    async with _client() as c:
        h = await auth_headers(c, f"{lower}@t.cz", plan=lower)
        r = await c.get(url, headers=h)
    assert r.status_code == 403, f"{url} s plánem {lower}: {r.status_code}"


@pytest.mark.asyncio
@pytest.mark.parametrize("url,min_tier", CASES)
async def test_sufficient_plan_200(url, min_tier):
    async with _client() as c:
        h = await auth_headers(c, f"{min_tier}@t.cz", plan=min_tier)
        r = await c.get(url, headers=h)
    assert r.status_code == 200, f"{url} s plánem {min_tier}: {r.status_code} {r.text[:120]}"


@pytest.mark.asyncio
async def test_free_plan_blocked_on_all(url=None):
    async with _client() as c:
        h = await auth_headers(c, "free@t.cz", plan="free")
        for u, _ in CASES:
            r = await c.get(u, headers=h)
            assert r.status_code == 403, f"free měl projít na {u}? {r.status_code}"


@pytest.mark.asyncio
async def test_admin_bypasses_paywall():
    # admin s plánem free musí projít všude (bypass)
    async with _client() as c:
        h = await auth_headers(c, "admin@t.cz", plan="free", admin=True)
        for u, _ in CASES:
            r = await c.get(u, headers=h)
            assert r.status_code == 200, f"admin neprošel na {u}? {r.status_code}"


@pytest.mark.asyncio
async def test_elite_passes_everything():
    async with _client() as c:
        h = await auth_headers(c, "elite@t.cz", plan="elite")
        for u, _ in CASES:
            r = await c.get(u, headers=h)
            assert r.status_code == 200, f"elite neprošel na {u}? {r.status_code}"


@pytest.mark.asyncio
async def test_bogus_token_401():
    async with _client() as c:
        r = await c.get("/api/discovery", headers={"Authorization": "Bearer totalne.podvrzeny.token"})
    assert r.status_code == 401
