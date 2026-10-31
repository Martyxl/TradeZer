"""Investorský deník: odhad dividend a rozložení portfolia vč. obsahu ETF."""
from datetime import date

from app.services.portfolio_insights import build_insights, project_dividends

TODAY = date(2026, 11, 1)
MO = {"dividends": [{"ex_date": "2026-09-15", "amount": 1.11}, {"ex_date": "2026-06-15", "amount": 1.06},
                    {"ex_date": "2026-03-25", "amount": 1.06}, {"ex_date": "2025-12-26", "amount": 1.06}],
      "announced": [], "sector": "Consumer Defensive", "country": "United States"}


def test_quarterly_projection_from_history():
    p = project_dividends(MO, TODAY)
    assert len(p) == 4 and all(x["status"] == "estimate" and x["amount"] == 1.11 for x in p)
    assert date(2026, 12, 1) <= p[0]["ex_date"] <= date(2026, 12, 31)


def test_announced_kept_and_stopped_payer_not_projected():
    msft = {"dividends": [{"ex_date": "2026-11-19", "amount": 0.98}, {"ex_date": "2026-08-20", "amount": 0.91},
                          {"ex_date": "2026-05-21", "amount": 0.91}]}
    p = project_dividends(msft, TODAY)
    assert p[0] == {"ex_date": date(2026, 11, 19), "amount": 0.98, "status": "announced"}
    assert all(x["amount"] == 0.98 for x in p) and len(p) == 4
    stopped = {"dividends": [{"ex_date": "2024-03-01", "amount": 0.5}, {"ex_date": "2024-06-01", "amount": 0.5}]}
    assert project_dividends(stopped, TODAY) == []
    assert project_dividends({}, TODAY) == []


def test_build_insights_etf_look_through():
    etf = {"type": "ETF", "etf": {"sectors": [{"sector": "Technology", "weight": 0.5}, {"sector": "Finance", "weight": 0.3}],
                                  "countries": [{"country": "China", "allocation": 1.0}],
                                  "top": [{"name": "Tencent", "weight": 0.1}]}}
    positions = [{"symbol": "MO", "name": "Altria", "quantity": 10, "currency": "USD", "value_base": 1000.0},
                 {"symbol": "KWBE", "name": "China ETF", "quantity": 5, "currency": "EUR", "value_base": 1000.0}]
    out = build_insights(positions, {"MO": MO, "KWBE": etf}, lambda a, c: a * 20 if c == "USD" else None, TODAY)
    sec = {r["name"]: r["pct"] for r in out["allocation"]["sectors"]}
    assert sec == {"Základní spotřeba": 50.0, "Technologie": 25.0, "Finance": 15.0, "Nezařazeno": 10.0}
    assert {r["name"]: r["pct"] for r in out["allocation"]["countries"]} == {"USA": 50.0, "Čína": 50.0}
    assert [r["name"] for r in out["allocation"]["top_exposure"]] == ["Altria", "Tencent"]
    d = out["dividends"]
    assert len(d["payments"]) == 4 and d["payments"][0]["gross"] == 11.1 and d["payments"][0]["gross_base"] == 222.0
    assert d["annual_base"] == 888.0 and d["yield_pct"] == 44.4


async def test_insights_endpoint(db_session):
    from datetime import datetime
    from httpx import ASGITransport, AsyncClient
    from app.db import get_session
    from app.main import app
    from app.models import InvestmentQuote, InvestmentTx, User
    from tests._auth import auth_headers

    async def _override():
        yield db_session
    app.dependency_overrides[get_session] = _override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            h = await auth_headers(c, "inv@x.cz")
            from sqlalchemy import select
            uid = await db_session.scalar(select(User.id).where(User.email == "inv@x.cz"))
            db_session.add_all([
                InvestmentTx(user_id=uid, symbol="MO", tx_type="buy", quantity=10, price=60, currency="USD", executed_at=datetime(2025, 1, 1)),
                InvestmentTx(user_id=uid, symbol="MO", tx_type="sell", quantity=2, price=70, currency="USD", executed_at=datetime(2025, 6, 1)),
                InvestmentQuote(symbol="MO", price=78.0), InvestmentQuote(symbol="USDCZK", price=21.8)])
            await db_session.commit()
            bad = await c.post("/api/investments/meta/ingest", json={"items": [{"symbol": "mo", **MO}]})
            assert bad.status_code in (401, 403, 503)
            from app.config import settings
            r = await c.post("/api/investments/meta/ingest", json={"items": [{"symbol": "mo", **MO, "junk": 1}]},
                             headers={"X-Internal-Token": settings.internal_api_token})
            assert r.json() == {"stored": 1}
            d = (await c.get("/api/investments/insights?base=CZK", headers=h)).json()
            assert d["base"] == "CZK" and d["has_meta"]
            assert d["allocation"]["sectors"][0]["name"] == "Základní spotřeba"
            assert d["dividends"]["payments"][0]["quantity"] == 8
            assert d["dividends"]["payments"][0]["gross_base"] == round(8 * 1.11 * 21.8, 2)
    finally:
        app.dependency_overrides.pop(get_session, None)
