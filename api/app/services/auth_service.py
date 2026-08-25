"""Autentizace bez externích závislostí: PBKDF2 hash hesla + HMAC-podepsaný token.

Hesla se NIKDY neukládají v plaintextu. Token je stateless (uid + expirace),
podepsaný AUTH_SECRET (fallback na INTERNAL_API_TOKEN). Bez JWT/passlib knihoven.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from app.config import settings

_ITER = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITER)
    return f"pbkdf2_sha256${_ITER}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _algo, iters, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


def _secret() -> bytes:
    return (os.environ.get("AUTH_SECRET") or settings.internal_api_token or "dev-only-secret").encode()


def make_token(user_id: int, days: int = 30) -> str:
    payload = {"uid": user_id, "exp": int(time.time()) + days * 86400}
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_token(token: str) -> int | None:
    return _verify(token, purpose="auth")


def make_reset_token(user_id: int, minutes: int = 60) -> str:
    """Krátkodobý (1h) token pro reset hesla — jiný purpose než login token."""
    payload = {"uid": user_id, "p": "reset", "exp": int(time.time()) + minutes * 60}
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_reset_token(token: str) -> int | None:
    return _verify(token, purpose="reset")


def _verify(token: str, purpose: str) -> int | None:
    try:
        body, sig = token.split(".")
        expected = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        pad = "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(body + pad))
        if int(payload.get("exp", 0)) < time.time():
            return None
        # login token nemá "p"; reset token má "p":"reset"
        if purpose == "reset" and payload.get("p") != "reset":
            return None
        if purpose == "auth" and payload.get("p") == "reset":
            return None
        return int(payload.get("uid"))
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
