"""Password hashing (Argon2id), JWT access tokens, opaque refresh tokens, API keys."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()  # Argon2id with library defaults (RFC 9106 low-memory profile)
# Verified against when a username does not exist, to keep login timing uniform.
_DUMMY_HASH = _hasher.hash("not-a-real-password")

JWT_ALG = "HS256"
JWT_ISSUER = "homelab-command-centre"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str | None) -> bool:
    try:
        return _hasher.verify(hashed or _DUMMY_HASH, password) and hashed is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    return _hasher.check_needs_rehash(hashed)


def validate_password_strength(password: str) -> str | None:
    """Return an error message, or None when the password is acceptable."""
    if len(password) < 12:
        return "Password must be at least 12 characters long"
    if len(password) > 256:
        return "Password must be at most 256 characters long"
    if len(set(password)) < 5:
        return "Password is too repetitive"
    return None


def create_access_token(secret: str, user_id: int, minutes: int, session_id: int | None) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iss": JWT_ISSUER,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
        "typ": "access",
        "sid": session_id,
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALG)


def decode_access_token(secret: str, token: str) -> dict[str, Any]:
    """Raises ``jwt.PyJWTError`` on any problem."""
    payload = jwt.decode(
        token,
        secret,
        algorithms=[JWT_ALG],
        issuer=JWT_ISSUER,
        options={"require": ["exp", "sub", "iss"]},
    )
    if payload.get("typ") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return payload


def new_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    """Refresh tokens/API keys are high-entropy random strings; SHA-256 is sufficient."""
    return hashlib.sha256(token.encode()).hexdigest()


def new_api_key() -> tuple[str, str]:
    """Return (full_key, prefix). The prefix is safe to display."""
    body = secrets.token_urlsafe(32)
    return f"hlcc_{body}", f"hlcc_{body[:6]}"


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
