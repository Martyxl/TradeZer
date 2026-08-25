"""Auth endpointy: registrace (email), login (email/username), profil, změna hesla.

Hesla hashovaná (PBKDF2), token HMAC-podepsaný (viz auth_service). Registrace
sbírá emaily zájemců i zakládá plnohodnotný účet (plan=free)."""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import User
from app.services.auth_service import (
    hash_password, verify_password, make_token, verify_token,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _user_out(u: User) -> dict:
    return {"id": u.id, "email": u.email, "username": u.username,
            "plan": u.plan, "is_admin": u.is_admin}


async def current_user(
    authorization: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
) -> User:
    token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    uid = verify_token(token)
    if not uid:
        raise HTTPException(status_code=401, detail="Neautorizováno")
    user = await session.get(User, uid)
    if not user:
        raise HTTPException(status_code=401, detail="Neautorizováno")
    return user


@router.post("/register")
async def register(payload: dict, session: AsyncSession = Depends(get_session)):
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Neplatný email")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Heslo musí mít aspoň 6 znaků")
    try:
        exists = await session.scalar(select(User).where(User.email == email))
        if exists:
            raise HTTPException(status_code=409, detail="Účet s tímto emailem už existuje")
        user = User(email=email, password_hash=hash_password(password), plan="free", is_admin=False)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — typicky výpadek DB; nešířit traceback ven
        import structlog
        structlog.get_logger().error("register failed", error=str(e))
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(status_code=503, detail="Registrace je dočasně nedostupná, zkus to prosím za chvíli.")
    return {"token": make_token(user.id), "user": _user_out(user)}


@router.post("/login")
async def login(payload: dict, session: AsyncSession = Depends(get_session)):
    ident = (payload.get("identifier") or payload.get("email") or "").strip()
    password = payload.get("password") or ""
    low = ident.lower()
    user = await session.scalar(
        select(User).where((User.email == low) | (User.username == ident))
    )
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Neplatné přihlašovací údaje")
    user.last_login = datetime.utcnow()
    user.login_count = (user.login_count or 0) + 1
    await session.commit()
    return {"token": make_token(user.id), "user": _user_out(user)}


@router.get("/me")
async def me(user: User = Depends(current_user)):
    return {"user": _user_out(user)}


@router.post("/change-password")
async def change_password(
    payload: dict,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    old = payload.get("old_password") or ""
    new = payload.get("new_password") or ""
    if not verify_password(old, user.password_hash):
        raise HTTPException(status_code=400, detail="Staré heslo nesedí")
    if len(new) < 6:
        raise HTTPException(status_code=400, detail="Nové heslo musí mít aspoň 6 znaků")
    user.password_hash = hash_password(new)
    await session.commit()
    return {"status": "ok"}


@router.post("/request-reset")
async def request_reset(payload: dict, session: AsyncSession = Depends(get_session)):
    """Self-service: uživatel zapomněl heslo → označí žádost, admin ji vyřídí v panelu.
    Vrací vždy generickou odpověď (neprozrazuje, jestli email existuje)."""
    email = (payload.get("email") or "").strip().lower()
    user = await session.scalar(select(User).where(User.email == email))
    if user is not None:
        user.reset_requested = True
        await session.commit()
    return {"status": "ok"}


async def require_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Přístup jen pro admina")
    return user


@router.get("/admin/overview")
async def admin_overview(_: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    """Admin přehled: registrace, plány, přihlášení, návštěvnost + seznam uživatelů."""
    from app.models import SiteCounter
    now = datetime.utcnow()

    async def count(where=None):
        stmt = select(func.count()).select_from(User)
        if where is not None:
            stmt = stmt.where(where)
        return int(await session.scalar(stmt) or 0)

    total = await count()
    pro = await count(User.plan == "pro")
    admins = await count(User.is_admin.is_(True))
    logins = int(await session.scalar(select(func.coalesce(func.sum(User.login_count), 0))) or 0)
    reg7 = await count(User.created_at >= now - timedelta(days=7))
    reg30 = await count(User.created_at >= now - timedelta(days=30))
    visits_row = await session.scalar(select(SiteCounter).where(SiteCounter.name == "page_visits"))
    visits = int(visits_row.value) if visits_row else 0

    reset_requests = await count(User.reset_requested.is_(True))

    rows = (await session.execute(select(User).order_by(User.created_at.desc()).limit(200))).scalars().all()
    users = [{
        "id": u.id, "email": u.email, "username": u.username, "plan": u.plan,
        "is_admin": u.is_admin, "login_count": u.login_count or 0,
        "reset_requested": u.reset_requested,
        "created_at": str(u.created_at)[:19] if u.created_at else None,
        "last_login": str(u.last_login)[:19] if u.last_login else None,
    } for u in rows]

    # registrace po dnech za 30 dní (pro graf)
    since30 = (now - timedelta(days=29)).date()
    by_day_rows = (await session.execute(
        select(func.date(User.created_at), func.count())
        .where(User.created_at >= now - timedelta(days=30))
        .group_by(func.date(User.created_at))
    )).all()
    counts = {str(d): int(n) for d, n in by_day_rows}
    reg_by_day = [{"date": str(since30 + timedelta(days=i)),
                   "count": counts.get(str(since30 + timedelta(days=i)), 0)} for i in range(30)]

    return {
        "stats": {
            "total_users": total, "pro": pro, "free": total - pro, "admins": admins,
            "logins_total": logins, "reg_7d": reg7, "reg_30d": reg30, "visits": visits,
            "reset_requests": reset_requests,
        },
        "users": users,
        "reg_by_day": reg_by_day,
        "payments": [],  # zatím žádné (platby nespuštěné)
    }


def _rand_password() -> str:
    return "tz-" + secrets.token_urlsafe(8)


@router.post("/admin/users/{user_id}/reset-password")
async def admin_reset_password(user_id: int, _: User = Depends(require_admin),
                               session: AsyncSession = Depends(get_session)):
    """Admin resetuje heslo uživateli → vygeneruje dočasné, vrátí ho (jen adminovi).
    Admin ho předá uživateli, ten si ho pak změní v /ucet."""
    u = await session.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    temp = _rand_password()
    u.password_hash = hash_password(temp)
    u.reset_requested = False
    await session.commit()
    return {"status": "ok", "temp_password": temp,
            "user": u.email or u.username}


@router.post("/admin/users/{user_id}/plan")
async def admin_set_plan(user_id: int, payload: dict, _: User = Depends(require_admin),
                         session: AsyncSession = Depends(get_session)):
    plan = (payload.get("plan") or "").strip().lower()
    if plan not in ("free", "pro"):
        raise HTTPException(status_code=400, detail="Plán musí být free nebo pro")
    u = await session.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    u.plan = plan
    await session.commit()
    return {"status": "ok", "plan": plan}


@router.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: int, admin: User = Depends(require_admin),
                            session: AsyncSession = Depends(get_session)):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Nemůžeš smazat sám sebe")
    u = await session.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    if u.is_admin:
        remaining = await session.scalar(select(func.count()).select_from(User).where(User.is_admin.is_(True)))
        if int(remaining or 0) <= 1:
            raise HTTPException(status_code=400, detail="Nelze smazat posledního admina")
    await session.delete(u)
    await session.commit()
    return {"status": "ok"}
