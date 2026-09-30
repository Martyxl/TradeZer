"""Sdílený test helper: registruj uživatele a vrať Bearer hlavičku (volitelně plán/admin)."""
from sqlalchemy import update

from app.models import User
from app.db.engine import engine


async def auth_headers(client, email: str, plan: str = "free", admin: bool = False) -> dict:
    r = await client.post("/api/auth/register", json={"email": email, "password": "secret123"})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    if plan != "free" or admin:
        async with engine.begin() as conn:
            await conn.execute(update(User).where(User.email == email).values(plan=plan, is_admin=admin))
    return {"Authorization": f"Bearer {token}"}
