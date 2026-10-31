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


@pytest.mark.asyncio
async def test_upcoming_ingest_and_pre_alert(outbox, monkeypatch):
    from app.valuation import earnings_alerts as A
    async with session_context() as s:
        s.add_all([ValInstrument(ticker="AMD", name="Advanced Micro Devices"), ValInstrument(ticker="PFE", name="Pfizer")])
        await s.commit()
    now = datetime.utcnow()
    soon = (now + timedelta(hours=20)).date()
    later = (now + timedelta(days=9)).date()
    # termín „za ~20 h“ = report_moment v okně PRE_HOURS bez ohledu na denní dobu testu
    monkeypatch.setattr(A, "report_moment", lambda u: now + (timedelta(hours=20) if u.report_date == soon else timedelta(days=9)))
    async with _client() as c:
        a_h = await auth_headers(c, "a@x.cz", plan="trader")
        b_h = await auth_headers(c, "b@x.cz", plan="trader")
        n_h = await auth_headers(c, "n@x.cz", plan="trader")
        await c.put("/api/valuation/earnings/alerts", json={"enabled": True, "scope": "all"}, headers=a_h)
        await c.put("/api/valuation/earnings/alerts", json={"enabled": True, "scope": "custom", "tickers": ["PFE"]}, headers=b_h)
        r = (await c.put("/api/valuation/earnings/alerts", json={"enabled": True, "pre_alerts": False}, headers=n_h)).json()
        assert r["pre_alerts"] is False
        body = {"items": [
            {"ticker": "AMD", "report_date": soon.isoformat(), "time_of_day": "amc", "eps_estimate": 1.68,
             "eps_low": 1.6, "eps_high": 1.8, "eps_year_ago": 1.2, "n_analysts": 30, "fiscal_quarter_end": "2026-09-30"},
            {"ticker": "PFE", "report_date": later.isoformat(), "time_of_day": "bmo", "eps_estimate": 0.72},
            {"ticker": "OLD", "report_date": "2020-01-01"},
        ]}
        res = (await c.post("/api/valuation/earnings/upcoming/ingest", json=body, headers=TOKEN)).json()
        assert res == {"stored": 2, "pre_alerts_sent": 1}
        assert [m["to"] for m in outbox] == ["a@x.cz"]           # b chce jen PFE, n má pre_alerts vypnuté
        assert "AMD" in outbox[0]["subject"] and "1,68" in outbox[0]["html"] and "po zavření" in outbox[0]["html"]
        # další ingest (za 6 h) už znovu neposílá
        assert (await c.post("/api/valuation/earnings/upcoming/ingest", json=body, headers=TOKEN)).json()["pre_alerts_sent"] == 0
        up = (await c.get("/api/valuation/earnings/upcoming", headers=a_h)).json()["items"]
        assert [u["ticker"] for u in up] == ["AMD", "PFE"] and up[0]["name"] == "Advanced Micro Devices"
        assert up[0]["eps_high"] == 1.8 and up[0]["time_of_day"] == "amc"


@pytest.mark.asyncio
async def test_analysts_ingest_and_detail():
    async with _client() as c:
        h = await auth_headers(c, "an@x.cz", plan="trader")
        assert (await c.get("/api/valuation/NVDA/analysts", headers=h)).status_code == 404
        item = {"ticker": "nvda", "price_target": {"average": 330, "current": 205, "upside_pct": 61},
                "revisions": [{"period": "current_year", "eps": 9.3, "chg_30d": 0.1, "up_month": 2, "down_month": 0}],
                "evil": "<script>", "holders": {"institutions": [], "funds": []}}
        r = await c.post("/api/valuation/analysts/ingest", json={"items": [item, {"ticker": "X"}]}, headers=TOKEN)
        assert r.json() == {"stored": 1}
        await c.post("/api/valuation/analysts/ingest", json={"items": [{**item, "growth": {"next_year": 70.9}}]}, headers=TOKEN)
        d = (await c.get("/api/valuation/NVDA/analysts", headers=h)).json()
        assert d["price_target"]["upside_pct"] == 61 and d["growth"]["next_year"] == 70.9 and "evil" not in d
        free = await auth_headers(c, "fr@x.cz")
        assert (await c.get("/api/valuation/NVDA/analysts", headers=free)).status_code == 403
