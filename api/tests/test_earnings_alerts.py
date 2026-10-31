"""E-mailová upozornění na výsledky hospodaření: nastavení odběru, výběr příjemců, dedup, odhlášení."""
import os
from datetime import datetime, timedelta

import pytest

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["INTERNAL_API_TOKEN"] = "test-token"

from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from app.main import app
from app.db.base import Base
from app.db.engine import engine
from app.db.session import session_context
from app.models import InvestmentTx, User
from app.valuation.models import ValEarningsAlertSub, ValInstrument
from app.services import email_service
from tests._auth import auth_headers

TOKEN = {"X-Internal-Token": "test-token"}
ANALYSIS = {"fiscal_period": "Q3 2026", "revenue_usd": 1.0e9, "verdict": "mixed", "eps_gaap": 1.0,
            "headline_cs": "Tržby rostou, zisk pod odhadem.", "summary_cs": ["Tržby +5 %"]}


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def outbox(monkeypatch):
    sent = []

    def fake_batch(msgs):
        sent.extend(msgs)
        return {m["to"] for m in msgs}
    monkeypatch.setattr(email_service, "send_batch", fake_batch)
    return sent


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _ingest(c, ticker, acc, analysis=ANALYSIS):
    body = {"ticker": ticker, "accession": acc, "accepted_at": (datetime.utcnow() - timedelta(minutes=5)).isoformat() + "Z",
            "url": "https://www.sec.gov/x", "analysis": analysis, "eps_estimate": 1.2}
    return (await c.post("/api/valuation/earnings/ingest", json=body, headers=TOKEN)).json()


@pytest.mark.asyncio
async def test_alert_recipients_dedup_and_unsubscribe(outbox):
    async with session_context() as s:
        s.add_all([ValInstrument(ticker="GOOGL", name="Alphabet Inc."), ValInstrument(ticker="MSFT", name="Microsoft")])
        await s.commit()
    async with _client() as c:
        all_h = await auth_headers(c, "all@x.cz", plan="trader")
        port_h = await auth_headers(c, "port@x.cz", plan="trader")
        cust_h = await auth_headers(c, "cust@x.cz", plan="trader")
        every_h = await auth_headers(c, "every@x.cz", plan="trader")
        free_h = await auth_headers(c, "free@x.cz")
        assert (await c.get("/api/valuation/earnings/alerts", headers=all_h)).json()["enabled"] is False
        assert (await c.put("/api/valuation/earnings/alerts", json={"enabled": True}, headers=free_h)).status_code == 403
        assert (await c.put("/api/valuation/earnings/alerts", json={"scope": "custom", "tickers": []},
                            headers=cust_h)).status_code == 422
        await c.put("/api/valuation/earnings/alerts", json={"enabled": True, "scope": "all"}, headers=all_h)
        await c.put("/api/valuation/earnings/alerts", json={"enabled": True, "scope": "portfolio"}, headers=port_h)
        r = (await c.put("/api/valuation/earnings/alerts", json={"enabled": True, "scope": "custom",
                         "tickers": ["msft", "msft", "<b>"]}, headers=cust_h)).json()
        assert r["tickers"] == ["MSFT", "B"]
        await c.put("/api/valuation/earnings/alerts", json={"enabled": True, "only_critical": False}, headers=every_h)

        # „port“ drží GOOGL
        async with session_context() as s:
            uid = await s.scalar(select(User.id).where(User.email == "port@x.cz"))
            s.add(InvestmentTx(user_id=uid, symbol="GOOGL", tx_type="buy", quantity=3, price=100,
                               currency="USD", executed_at=datetime.utcnow()))
            await s.commit()

        # kritický (smíšený) report GOOGL → all + port + every; custom (MSFT) ne
        rep = await _ingest(c, "GOOGL", "acc-1")
        to = sorted(m["to"] for m in outbox)
        assert to == ["all@x.cz", "every@x.cz", "port@x.cz"]
        assert "GOOGL" in outbox[0]["subject"] and "Alphabet" in outbox[0]["html"]
        assert "unsubscribe?token=" in outbox[0]["headers"]["List-Unsubscribe"]
        # reakce ceny → nic znovu
        await c.post(f"/api/valuation/earnings/{rep['id']}/reaction", json={"price_before": 100, "price_now": 90}, headers=TOKEN)
        assert len(outbox) == 3

        # neutrální MSFT bez pohybu → jen „every“ (chce všechny výsledky)
        outbox.clear()
        rep2 = await _ingest(c, "MSFT", "acc-2", {**ANALYSIS, "verdict": "neutral"})
        assert [m["to"] for m in outbox] == ["every@x.cz"]
        # akcie pak pohne o 5 % → kritické → all + cust (MSFT), every už ne
        outbox.clear()
        await c.post(f"/api/valuation/earnings/{rep2['id']}/reaction", json={"price_before": 100, "price_now": 105}, headers=TOKEN)
        assert sorted(m["to"] for m in outbox) == ["all@x.cz", "cust@x.cz"]

        # odhlášení odkazem z e-mailu (bez přihlášení)
        async with session_context() as s:
            tok = (await s.execute(select(ValEarningsAlertSub.unsubscribe_token))).scalars().first()
        u = await c.get(f"/api/valuation/earnings/alerts/unsubscribe?token={tok}")
        assert u.status_code == 200 and "zrušený" in u.text
        bad = await c.get("/api/valuation/earnings/alerts/unsubscribe?token=" + "x" * 30)
        assert "není platný" in bad.text

        # zkušební e-mail jen sobě, max 1× za minutu
        outbox.clear()
        t = await c.post("/api/valuation/earnings/alerts/test", headers=cust_h)
        assert t.status_code == 200 and [m["to"] for m in outbox] == ["cust@x.cz"]
        assert (await c.post("/api/valuation/earnings/alerts/test", headers=cust_h)).status_code == 429
