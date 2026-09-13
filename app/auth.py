"""Authentication helpers for local password and magic-link login."""

from __future__ import annotations

from http.cookies import CookieError, SimpleCookie
import hashlib
import hmac
import secrets
import time
from typing import Any

import jwt
from fastapi import Request
from jwt import InvalidTokenError

from app.config import Settings


AUTH_COOKIE_NAME = "armory_session"
AUTH_SESSION_ISSUER = "armory"
PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 600_000
PASSWORD_SALT_BYTES = 16

AUTH_PROXY_HEADERS = (
    "x-forwarded-email",
    "x-forwarded-user",
    "x-forwarded-preferred-username",
    "x-forwarded-access-token",
    "remote-user",
    "remote-email",
)


def normalize_email(value: str | None) -> str:
    """Normalize an email for allowlist and identity comparisons."""
    return (value or "").strip().casefold()


def allowed_emails(settings: Settings) -> set[str]:
    return {
        normalize_email(item)
        for item in settings.auth_allowed_emails.split(",")
        if normalize_email(item)
    }


def is_allowed_email(email: str | None, settings: Settings) -> bool:
    return normalize_email(email) in allowed_emails(settings)


def hash_password(password: str) -> str:
    """Create a salted password hash without storing the password itself."""
    salt = secrets.token_bytes(PASSWORD_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    return "$".join(
        (
            PASSWORD_HASH_ALGORITHM,
            str(PASSWORD_HASH_ITERATIONS),
            salt.hex(),
            digest.hex(),
        )
    )


def verify_password(password: str, encoded_hash: str | None) -> bool:
    """Verify a password hash while safely rejecting malformed stored values."""
    if not encoded_hash:
        return False

    try:
        algorithm, iterations_text, salt_text, digest_text = encoded_hash.split("$")
        iterations = int(iterations_text)
        salt = bytes.fromhex(salt_text)
        expected_digest = bytes.fromhex(digest_text)
    except (TypeError, ValueError, OverflowError):
        return False

    if (
        algorithm != PASSWORD_HASH_ALGORITHM
        or not 100_000 <= iterations <= 2_000_000
        or len(salt) != PASSWORD_SALT_BYTES
        or len(expected_digest) != hashlib.sha256().digest_size
    ):
        return False

    actual_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual_digest, expected_digest)


def create_session_token(email: str, settings: Settings) -> str:
    if not settings.auth_secret:
        raise RuntimeError("AUTH_SECRET is not configured")

    now = int(time.time())
    expires_at = now + settings.auth_session_days * 24 * 60 * 60
    payload = {
        "iss": AUTH_SESSION_ISSUER,
        "sub": normalize_email(email),
        "iat": now,
        "exp": expires_at,
        "typ": "session",
    }
    return jwt.encode(payload, settings.auth_secret, algorithm="HS256")


def decode_session_token(token: str | None, settings: Settings) -> str | None:
    if not token or not settings.auth_secret:
        return None

    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.auth_secret,
            algorithms=["HS256"],
            issuer=AUTH_SESSION_ISSUER,
            options={"require": ["iss", "sub", "iat", "exp"]},
        )
    except InvalidTokenError:
        return None

    email = normalize_email(payload.get("sub"))
    if payload.get("typ", "session") != "session" or not is_allowed_email(email, settings):
        return None
    return email


def _scope_headers(scope: dict) -> dict[str, str]:
    return {
        name.decode("latin-1").lower(): value.decode("latin-1")
        for name, value in scope.get("headers", [])
    }


def get_email_from_scope(scope: dict, settings: Settings) -> str | None:
    """Resolve the authenticated identity without trusting user headers in magic-link mode."""
    headers = _scope_headers(scope)

    if settings.auth_mode.casefold() == "proxy":
        for header in AUTH_PROXY_HEADERS:
            value = normalize_email(headers.get(header))
            if value:
                return value
        return None

    cookie = SimpleCookie()
    try:
        cookie.load(headers.get("cookie", ""))
    except (CookieError, ValueError):
        return None
    session = cookie.get(AUTH_COOKIE_NAME)
    return decode_session_token(session.value if session else None, settings)


def get_current_email(request: Request) -> str:
    """Return the current identity used by comments, affairs and task history."""
    state_email = normalize_email(getattr(request.state, "user_email", None))
    if state_email:
        return state_email

    settings = request.app.state.settings
    if settings.auth_mode.casefold() == "proxy":
        for header in AUTH_PROXY_HEADERS:
            value = normalize_email(request.headers.get(header))
            if value:
                return value

    return "local.user"


def is_safe_next_path(value: str | None) -> bool:
    return bool(value and value.startswith("/") and not value.startswith("//"))


def safe_next_path(value: str | None) -> str:
    return value if is_safe_next_path(value) else "/"
