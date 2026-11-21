"""Smart Money / Fondy: parsování 13F, porovnání čtvrtletí (split ≠ nákup), konsenzus, 13D/G, endpointy."""
import os
import sys

import pytest

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["INTERNAL_API_TOKEN"] = "test-token"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "data"))

from fund_holdings_scan import build, compare, norm_name, parse_infotable, parse_percent, ticker_by_name  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.engine import engine  # noqa: E402
from app.main import app  # noqa: E402
from tests._auth import auth_headers  # noqa: E402

XML = """<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
<infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>037833100</cusip>
 <value>600</value><shrsOrPrnAmt><sshPrnamt>3</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
<infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>037833100</cusip>
 <value>400</value><shrsOrPrnAmt><sshPrnamt>2</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
<infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>PUT</titleOfClass><cusip>037833100</cusip>
 <value>999</value><shrsOrPrnAmt><sshPrnamt>9</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt><putCall>Put</putCall></infoTable>
<infoTable><nameOfIssuer>X CORP NOTE</nameOfIssuer><titleOfClass>NOTE</titleOfClass><cusip>111111111</cusip>
 <value>50</value><shrsOrPrnAmt><sshPrnamt>50</sshPrnamt><sshPrnamtType>PRN</sshPrnamtType></shrsOrPrnAmt></infoTable>
</informationTable>"""


def h(value, shares, name="X"):
    return {"name": name, "value": value, "shares": shares}


def test_parse_sums_managers_and_skips_options_and_bonds():
    assert parse_infotable(XML) == {"037833100": {"name": "APPLE INC", "value": 1000.0, "shares": 5.0}}
    assert parse_infotable("<broken") == {}


def test_compare_actions_and_split():
    prev = {"A": h(100, 10), "B": h(100, 10), "C": h(100, 10), "D": h(100, 10), "S": h(100, 10)}
    cur = {"A": h(200, 20), "B": h(50, 5), "C": h(104, 10.4), "N": h(100, 1), "S": h(110, 40)}
    r = {x["cusip"]: x for x in compare(cur, prev)}
    assert r["A"]["action"] == "added" and r["A"]["chg_pct"] == 100 and r["A"]["flow"] == 100
    assert r["B"]["action"] == "reduced" and r["B"]["flow"] == -50
    assert r["C"]["action"] == "hold"                         # +4 % = šum
    assert r["N"]["action"] == "new" and r["N"]["flow"] == 100
    assert r["D"]["action"] == "sold" and r["D"]["flow"] == -100 and r["D"]["prev_weight"] == 20
    assert r["S"]["action"] == "hold"                         # split 4:1, hodnota stejná
    assert all(x["action"] == "hold" for x in compare(cur, None))


def test_build_consensus_ignores_small_and_stale_positions():
    big = {"A": h(5000, 50), "B": h(4900, 49), "T": h(100, 1)}
    funds = [
        {"key": "f1", "name": "F1", "manager": "m", "style": "value", "cik": 1, "period": "2026-09-30",
         "filed": "2026-11-14", "prev_period": "2026-06-30", "holdings": {**big, "N": h(1000, 10)}, "prev": big},
        {"key": "f2", "name": "F2", "manager": "m", "style": "value", "cik": 2, "period": "2026-09-30",
         "filed": "2026-11-14", "prev_period": "2026-06-30", "holdings": {"N": h(500, 5), "A": h(10, 1)},
         "prev": {"N": h(250, 2.5), "A": h(10, 1), "B": h(5000, 50)}},
        # starý výpis (fond přestal podávat) → do konsenzu nepatří, i když „kupoval“
        {"key": "f3", "name": "F3", "manager": "m", "style": "value", "cik": 3, "period": "2025-09-30",
         "filed": "2025-11-14", "prev_period": "2025-06-30", "holdings": {"N": h(500, 5)}, "prev": {}},
    ]
    out = build(funds, {"A": "AAA", "B": "BBB", "N": "NNN", "T": "TTT"}, [])
    assert out["quarter"] == "2026-09-30"
    buys = {c["ticker"]: c for c in out["consensus_buys"]}
    assert buys["NNN"]["count"] == 2 and buys["NNN"]["new"] == 1 and "TTT" not in buys
    assert [m[0] for m in buys["NNN"]["funds"]] == ["f1", "f2"]
    assert out["consensus_sells"][0]["ticker"] == "BBB" and out["consensus_sells"][0]["exits"] == 1
    f3 = next(f for f in out["funds"] if f["key"] == "f3")
    assert f3["stale"] and out["by_ticker"]["NNN"]["hc"] == 3
    assert out["most_held"][0]["ticker"] in ("NNN", "AAA")


def test_parse_percent():
    assert parse_percent("<a><percentOfClass>5.2</percentOfClass><percentOfClass>7.1</percentOfClass></a>") == 7.1
    assert parse_percent("<ns:classPercent> 9.9</ns:classPercent>") == 9.9
    assert parse_percent("plain text 13D") is None


@pytest.fixture
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_funds_endpoints(db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        hd = await auth_headers(c, "pro@t.cz", plan="pro")
        assert (await c.get("/api/smart-money/funds", headers=hd)).json()["funds"] == []
        assert (await c.post("/api/smart-money/funds/ingest", json={"funds": [{"key": "x"}]})).status_code == 401
        bad = await c.post("/api/smart-money/funds/ingest", json={"funds": []}, headers={"X-Internal-Token": "test-token"})
        assert bad.json()["status"] == "error"
        ok = await c.post("/api/smart-money/funds/ingest", json={"funds": [{"key": "x"}], "stakes": [{}]},
                          headers={"X-Internal-Token": "test-token"})
        assert ok.json() == {"status": "ok", "funds": 1, "stakes": 1}
        got = (await c.get("/api/smart-money/funds", headers=hd)).json()
        assert got["funds"] == [{"key": "x"}] and got["generated"]
        # insider snapshot je oddělený
        assert (await c.get("/api/smart-money", headers=hd)).json()["insiders"] == []


def test_ticker_fallback_by_issuer_name():
    assert norm_name("ASML HLDG NV") == norm_name("ASML Holding N.V.") == "ASML"
    assert norm_name("TEVA PHARMACEUTICAL INDS LTD") == norm_name("Teva Pharmaceutical Industries Ltd")
    sec = {norm_name(n): t for n, t in (("ASML Holding N.V.", "ASML"), ("Seagate Technology Holdings plc", "STX"),
                                        ("Alphabet Inc.", "GOOGL"), ("Nu Holdings Ltd.", "NU"))}
    names = {"N07059210": "ASML HLDG NV", "G7997R103": "SEAGATE TECHNOLOGY HLDNGS PL", "02079K305": "ALPHABET INC",
             "02079K404": "ALPHABET INC", "G6683N103": "NU HLDGS LTD", "X": "UNKNOWN THING CORP"}
    out = ticker_by_name(names, {"02079K305": "GOOG"}, sec)
    # chybný CUSIP Alphabetu převezme ticker od správného CUSIPu téhož emitenta ve výpisech
    assert out == {"N07059210": "ASML", "G7997R103": "STX", "02079K404": "GOOG", "G6683N103": "NU"}
