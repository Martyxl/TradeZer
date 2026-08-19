"""Auth endpointy: registrace (email), login (email/username), profil, změna hesla.

Hesla hashovaná (PBKDF2), token HMAC-podepsaný (viz auth_service). Registrace
sbírá emaily zájemců i zakládá plnohodnotný účet (plan=free)."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
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
    exists = await session.scalar(select(User).where(User.email == email))
    if exists:
        raise HTTPException(status_code=409, detail="Účet s tímto emailem už existuje")
    user = User(email=email, password_hash=hash_password(password), plan="free", is_admin=False)
    session.add(user)
    await session.commit()
    await session.refresh(user)
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
