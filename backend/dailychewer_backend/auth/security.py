"""Password hashing and JWT helpers."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import secrets

from dailychewer_backend.config import load_settings

try:
    from passlib.context import CryptContext  # type: ignore
except Exception:  # pragma: no cover - fallback path
    CryptContext = None

try:
    from jose import jwt  # type: ignore
except Exception:  # pragma: no cover - fallback path
    jwt = None


PWD_CONTEXT = CryptContext(schemes=["bcrypt"], deprecated="auto") if CryptContext else None


def hash_password(password: str) -> str:
    """Hash one plaintext password."""

    if PWD_CONTEXT is not None:
        return PWD_CONTEXT.hash(password)
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 600000)
    return f"pbkdf2_sha256${salt}${base64.urlsafe_b64encode(digest).decode('utf-8')}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify one plaintext password against its stored hash."""

    if password_hash.startswith("pbkdf2_sha256$"):
        _, salt, encoded = password_hash.split("$", maxsplit=2)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 600000)
        return hmac.compare_digest(base64.urlsafe_b64encode(digest).decode("utf-8"), encoded)
    if PWD_CONTEXT is None:
        return False
    return PWD_CONTEXT.verify(password, password_hash)


def _b64url_encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("utf-8")


def _b64url_decode(payload: str) -> bytes:
    padding = "=" * (-len(payload) % 4)
    return base64.urlsafe_b64decode(payload + padding)


def create_access_token(user_id: str, username: str) -> str:
    """Create one signed JWT access token."""

    settings = load_settings()
    secret = settings.database.jwt_secret_key
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY is required for auth-enabled web mode.")
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.database.jwt_expire_minutes)
    payload = {
        "sub": user_id,
        "username": username,
        "exp": int(expires_at.timestamp()),
    }
    if jwt is not None:
        return jwt.encode(payload, secret, algorithm=settings.database.jwt_algorithm)
    header = {"alg": settings.database.jwt_algorithm, "typ": "JWT"}
    signing_input = ".".join(
        [
            _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8")),
            _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
        ]
    )
    signature = hmac.new(secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url_encode(signature)}"


def decode_access_token(token: str) -> dict:
    """Decode one signed JWT access token."""

    settings = load_settings()
    secret = settings.database.jwt_secret_key
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY is required for auth-enabled web mode.")
    if jwt is not None:
        return jwt.decode(token, secret, algorithms=[settings.database.jwt_algorithm])
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid token format.")
    signing_input = ".".join(parts[:2])
    expected_signature = hmac.new(secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest()
    actual_signature = _b64url_decode(parts[2])
    if not hmac.compare_digest(expected_signature, actual_signature):
        raise ValueError("Invalid token signature.")
    payload = json.loads(_b64url_decode(parts[1]).decode("utf-8"))
    if int(payload.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
        raise ValueError("Token expired.")
    return payload
