"""Chatovací pomocník: fronta otázek pro Spark, limit, vlastnictví, sestavení promptu, shoda s Legendou."""
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["ANTHROPIC_API_KEY"] = "test-key"
os.environ["INTERNAL_API_TOKEN"] = "test-token"

from httpx import AsyncClient, ASGITransport
from sqlalchemy import update

from app.main import app
from app.db.base import Base
from app.db.engine import engine
from app.models import HelpChatMessage
from app.routers import help as help_router
from tests._auth import auth_headers

TOKEN = {"X-Internal-Token": "test-token"}


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
async def test_full_roundtrip_ask_worker_answer():
    async with _client() as c:
        h = await auth_headers(c, "u@x.cz")
        assert (await c.post("/api/help/ask", json={"page": "/discovery", "question": "Co je skóre?"})).status_code == 401
        r = await c.post("/api/help/ask", json={"page": "/discovery?x=1", "question": "Co znamená skóre na Discovery?"}, headers=h)
        mid = r.json()["id"]
        assert (await c.get(f"/api/help/ask/{mid}", headers=h)).json()["status"] == "queued"
        assert (await c.get("/api/help/pending")).status_code == 401
        items = (await c.get("/api/help/pending", headers=TOKEN)).json()["items"]
        assert [i["id"] for i in items] == [mid]
        msgs = items[0]["messages"]
        assert msgs[0]["role"] == "system" and "Discovery skóre" in msgs[0]["content"]
        assert "Stránka, na které je uživatel (/discovery)" in msgs[0]["content"]
        assert msgs[-1] == {"role": "user", "content": "Co znamená skóre na Discovery?"}
        assert (await c.get("/api/help/pending", headers=TOKEN)).json()["items"] == []   # už je working
        await c.post("/api/help/answer", json={"id": mid, "answer": "Skóre je heuristika 0–100…", "model": "heavy", "ms": 900}, headers=TOKEN)
        got = (await c.get(f"/api/help/ask/{mid}", headers=h)).json()
        assert got["status"] == "done" and got["answer"].startswith("Skóre")
        # cizí uživatel odpověď nevidí
        other = await auth_headers(c, "o@x.cz")
        assert (await c.get(f"/api/help/ask/{mid}", headers=other)).status_code == 404


@pytest.mark.asyncio
async def test_followup_includes_recent_history():
    async with _client() as c:
        h = await auth_headers(c, "u@x.cz")
        m1 = (await c.post("/api/help/ask", json={"page": "/valuation", "question": "Co je PEG?"}, headers=h)).json()["id"]
        await c.get("/api/help/pending", headers=TOKEN)
        await c.post("/api/help/answer", json={"id": m1, "answer": "PEG je P/E děleno růstem."}, headers=TOKEN)
        await c.post("/api/help/ask", json={"page": "/valuation", "question": "A kolik je dobré?"}, headers=h)
        msgs = (await c.get("/api/help/pending", headers=TOKEN)).json()["items"][0]["messages"]
        assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
        assert msgs[2]["content"] == "PEG je P/E děleno růstem."


@pytest.mark.asyncio
async def test_validation_limit_and_expiry(monkeypatch):
    monkeypatch.setattr(help_router, "DAILY_LIMIT", 2)
    async with _client() as c:
        h = await auth_headers(c, "u@x.cz")
        assert (await c.post("/api/help/ask", json={"question": " "}, headers=h)).status_code == 422
        assert (await c.post("/api/help/ask", json={"question": "x" * 900}, headers=h)).status_code == 422
        ids = [(await c.post("/api/help/ask", json={"question": f"otázka {i}"}, headers=h)).json()["id"] for i in range(2)]
        assert (await c.post("/api/help/ask", json={"question": "třetí"}, headers=h)).status_code == 429
        async with engine.begin() as conn:   # otázka čeká déle než TTL → propadne
            await conn.execute(update(HelpChatMessage).where(HelpChatMessage.id == ids[0])
                               .values(created_at=datetime.utcnow() - timedelta(minutes=5)))
        assert (await c.get(f"/api/help/ask/{ids[0]}", headers=h)).json()["status"] == "expired"
        items = (await c.get("/api/help/pending", headers=TOKEN)).json()["items"]
        assert [i["id"] for i in items] == [ids[1]]


def test_glossary_module_matches_legend():
    """Legenda je zdroj pravdy — po její úpravě spustit api/scripts/sync_glossary.py."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("sync_glossary", Path(__file__).resolve().parents[1] / "scripts" / "sync_glossary.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from app.help.glossary_data import GLOSSARY
    assert GLOSSARY == mod.parse_terms(mod.LEGEND.read_text(encoding="utf-8"))
    assert len(GLOSSARY) >= 70


def test_every_sidebar_page_has_description():
    from app.help.pages import PAGES
    sidebar = (Path(__file__).resolve().parents[2] / "web" / "components" / "Sidebar.tsx").read_text(encoding="utf-8")
    hrefs = set(re.findall(r'href: "(/[a-z\-]+)"', sidebar))
    assert hrefs and hrefs <= set(PAGES), hrefs - set(PAGES)
