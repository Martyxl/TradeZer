"""Admin pošta: synchronizace z Resendu (bez duplikátů), čtení, odpověď ve vlákně, jen pro admina."""
import json
import os

import httpx
import pytest
import respx

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["ANTHROPIC_API_KEY"] = "test-key"
os.environ["INTERNAL_API_TOKEN"] = "test-token"
os.environ["RESEND_API_KEY"] = "re_test"

from httpx import AsyncClient, ASGITransport

from app.main import app
from app.db.base import Base
from app.db.engine import engine
from tests._auth import auth_headers

R = "https://api.resend.com"


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _received(rid, subject, minutes, msg_id, references=None):
    headers = {"from": "Twelve Data Sales <sales@twelvedata.com>"}
    if references:
        headers["references"] = references
        headers["in-reply-to"] = references.split()[-1]
    return {"id": rid, "from": "sales@twelvedata.com", "to": ["info@tradezer.app"], "cc": [],
            "subject": subject, "text": f"Text {subject}", "html": f"<p>{subject}</p>",
            "headers": headers, "message_id": msg_id, "created_at": f"2026-10-26T10:{minutes:02d}:00Z",
            "attachments": [{"id": "att1", "filename": "price.pdf", "size": 1000, "content_type": "application/pdf"}]}


def _mock_resend(emails):
    respx.get(f"{R}/emails/receiving").mock(return_value=httpx.Response(200, json={
        "object": "list", "has_more": False,
        "data": [{"id": e["id"], "subject": e["subject"]} for e in emails]}))
    for e in emails:
        respx.get(f"{R}/emails/receiving/{e['id']}").mock(return_value=httpx.Response(200, json=e))


@pytest.mark.asyncio
@respx.mock
async def test_sync_is_idempotent_and_parses_sender():
    emails = [_received("r2", "Re: licence", 5, "<b@td>"), _received("r1", "Licence quote", 1, "<a@td>")]
    _mock_resend(emails)
    async with _client() as c:
        h = await auth_headers(c, "admin@x.cz", admin=True)
        assert (await c.post("/api/admin/mail/sync", headers=h)).json() == {"added": 2}
        assert (await c.post("/api/admin/mail/sync", headers=h)).json() == {"added": 0}   # žádné duplicity
        lst = (await c.get("/api/admin/mail?folder=in", headers=h)).json()
        assert lst["unread"] == 2 and [i["subject"] for i in lst["items"]] == ["Re: licence", "Licence quote"]
        it = lst["items"][0]
        assert it["from_name"] == "Twelve Data Sales" and it["from_addr"] == "sales@twelvedata.com" and it["has_attachments"]
        detail = (await c.get(f"/api/admin/mail/{it['id']}", headers=h)).json()
        assert detail["text"] == "Text Re: licence" and detail["attachments"][0]["filename"] == "price.pdf"
        assert (await c.get("/api/admin/mail?folder=in", headers=h)).json()["unread"] == 1      # otevřením přečteno


@pytest.mark.asyncio
@respx.mock
async def test_reply_threads_with_headers_and_is_stored():
    _mock_resend([_received("r1", "Licence quote", 1, "<a@td>")])
    sent = respx.post(f"{R}/emails").mock(return_value=httpx.Response(200, json={"id": "s1"}))
    async with _client() as c:
        h = await auth_headers(c, "admin@x.cz", admin=True)
        await c.post("/api/admin/mail/sync", headers=h)
        mid = (await c.get("/api/admin/mail", headers=h)).json()["items"][0]["id"]
        r = await c.post("/api/admin/mail/send", headers=h, json={
            "to": "sales@twelvedata.com", "subject": "Re: Licence quote", "text": "Díky <b>!</b>", "reply_to_id": mid})
        assert r.json()["status"] == "sent"
        body = json.loads(sent.calls.last.request.content)
        assert body["headers"] == {"In-Reply-To": "<a@td>", "References": "<a@td>"}
        assert body["from"] == "Tradezer <info@tradezer.app>" and "&lt;b&gt;" in body["html"]   # text escapován
        out = (await c.get("/api/admin/mail?folder=out", headers=h)).json()["items"]
        assert out[0]["subject"] == "Re: Licence quote"
        thread = (await c.get(f"/api/admin/mail/{mid}", headers=h)).json()["thread"]
        assert [t["direction"] for t in thread] == ["out"]


@pytest.mark.asyncio
@respx.mock
async def test_send_validation_and_admin_only():
    async with _client() as c:
        user = await auth_headers(c, "u@x.cz")
        assert (await c.get("/api/admin/mail", headers=user)).status_code == 403
        assert (await c.post("/api/admin/mail/send", headers=user, json={"to": "a@b.cz"})).status_code == 403
        h = await auth_headers(c, "admin@x.cz", admin=True)
        bad = await c.post("/api/admin/mail/send", headers=h, json={"to": "neni-email", "subject": "x", "text": "y"})
        assert bad.status_code == 422
        assert (await c.post("/api/admin/mail/send", headers=h, json={"to": "a@b.cz", "subject": "", "text": "y"})).status_code == 422


@pytest.mark.asyncio
@respx.mock
async def test_restricted_key_gives_clear_error():
    respx.get(f"{R}/emails/receiving").mock(return_value=httpx.Response(401, json={"message": "restricted"}))
    async with _client() as c:
        h = await auth_headers(c, "admin@x.cz", admin=True)
        r = await c.post("/api/admin/mail/sync", headers=h)
        assert r.status_code == 502 and "plným přístupem" in r.json()["detail"]
