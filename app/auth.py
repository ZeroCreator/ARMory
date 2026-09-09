"""Authentication helpers for the optional local magic-link login."""

from __future__ import annotations

from http.cookies import CookieError, SimpleCookie
import time
from typing import Any

import jwt
from fastapi import Request
from jwt import InvalidTokenError

from app.config import Settings


AUTH_COOKIE_NAME = "armory_session"
AUTH_SESSION_ISSUER = "armory"

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
