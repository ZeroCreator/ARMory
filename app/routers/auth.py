"""Local email magic-link authentication for a standalone ARMory instance."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr
import hashlib
import logging
import secrets
import smtplib
import ssl
import time
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    AUTH_COOKIE_NAME,
    create_session_token,
    get_current_email,
    is_allowed_email,
    normalize_email,
    safe_next_path,
)
from app.database import get_db
from app.models import AuthLoginToken


router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)

_RATE_LIMIT_WINDOW_SECONDS = 15 * 60
_RATE_LIMIT_MAX_ATTEMPTS = 5
_request_attempts: dict[str, list[float]] = {}


def _render_login(
    request: Request,
    *,
    next_path: str = "/",
    message: str | None = None,
    error: str | None = None,
):
    return request.app.state.templates.TemplateResponse(
        "auth/login.html",
        {
            "request": request,
            "title": "Вход в ARMory",
            "next_path": safe_next_path(next_path),
            "message": message,
            "error": error,
        },
    )


def _submitted_email(value: str) -> str | None:
    email = normalize_email(value)
    if not email or any(character.isspace() for character in email):
        return None
    local_part, separator, domain = email.rpartition("@")
    if not separator or not local_part or not domain or "." not in domain:
        return None
    return email


def _request_ip(request: Request) -> str:
    forwarded = request.headers.get("x-real-ip")
    if forwarded:
        return forwarded.strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


def _rate_limited(key: str) -> bool:
    now = time.monotonic()
    recent = [stamp for stamp in _request_attempts.get(key, []) if now - stamp < _RATE_LIMIT_WINDOW_SECONDS]
    recent.append(now)
    _request_attempts[key] = recent
    if len(_request_attempts) > 1000:
        cutoff = now - _RATE_LIMIT_WINDOW_SECONDS
        for old_key in [item for item, stamps in _request_attempts.items() if not stamps or stamps[-1] < cutoff]:
            _request_attempts.pop(old_key, None)
    return len(recent) > _RATE_LIMIT_MAX_ATTEMPTS


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _public_base_url(request: Request) -> str:
    settings = request.app.state.settings
    if settings.auth_public_url:
        return settings.auth_public_url.rstrip("/")

    scheme = request.headers.get("x-forwarded-proto", request.url.scheme).split(",", 1)[0].strip()
    host = request.headers.get("host", request.url.netloc)
    return f"{scheme}://{host}".rstrip("/")


def _login_link(request: Request, token: str, next_path: str) -> str:
    query = urlencode({"token": token, "next": safe_next_path(next_path)})
    return f"{_public_base_url(request)}/auth/verify?{query}"


def _send_login_email(settings, recipient: str, link: str, ttl_minutes: int) -> None:
    if not settings.smtp_host or not settings.smtp_user or not settings.smtp_password:
        raise RuntimeError("SMTP settings are incomplete")

    sender = settings.smtp_from_email or settings.smtp_user
    message = EmailMessage()
    message["Subject"] = "Ссылка для входа в ARMory"
    message["From"] = formataddr((settings.smtp_from_name, sender))
    message["To"] = recipient
    message.set_content(
        "Здравствуйте!\n\n"
        f"Перейдите по ссылке, чтобы войти в ARMory. Ссылка действует {ttl_minutes} минут:\n\n"
        f"{link}\n\n"
        "Если вы не запрашивали вход, просто проигнорируйте это письмо."
    )

    tls_context = ssl.create_default_context()
    if settings.smtp_use_ssl:
        with smtplib.SMTP_SSL(
            settings.smtp_host,
            settings.smtp_port,
            context=tls_context,
            timeout=20,
        ) as smtp:
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
        return

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls(context=tls_context)
        smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)


@router.get("/login")
async def login_page(request: Request, next: str = "/"):
    current_email = normalize_email(get_current_email(request))
    if current_email and current_email != "local.user":
        return RedirectResponse(safe_next_path(next), status_code=303)
    return _render_login(request, next_path=next)


@router.post("/request")
async def request_login_link(
    request: Request,
    email: str = Form(...),
    next: str = Form("/"),
    db: AsyncSession = Depends(get_db),
):
    settings = request.app.state.settings
    next_path = safe_next_path(next)
    submitted = _submitted_email(email)
    if not submitted:
        return _render_login(request, next_path=next_path, error="Введите корректный адрес электронной почты.")

    generic_message = (
        "Если этот адрес добавлен в список доступа, письмо со ссылкой уже отправлено. "
        "Проверьте входящие и папку «Спам»."
    )
    rate_key = f"{_request_ip(request)}:{submitted}"
    if not is_allowed_email(submitted, settings) or _rate_limited(rate_key):
        return _render_login(request, next_path=next_path, message=generic_message)

    if not settings.auth_secret:
        logger.error("Cannot issue an ARMory login link: AUTH_SECRET is not configured")
        return _render_login(request, next_path=next_path, error="Авторизация временно не настроена.")

    token = secrets.token_urlsafe(32)
    login_token = AuthLoginToken(
        email=submitted,
        token_hash=_token_hash(token),
        expires_at=datetime.utcnow() + timedelta(minutes=settings.auth_link_ttl_minutes),
    )
    db.add(login_token)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception("Failed to create an ARMory login token")
        return _render_login(request, next_path=next_path, error="Не удалось подготовить ссылку входа.")

    try:
        await asyncio.to_thread(
            _send_login_email,
            settings,
            submitted,
            _login_link(request, token, next_path),
            settings.auth_link_ttl_minutes,
        )
    except Exception:
        logger.exception("Failed to send an ARMory login email")
        return _render_login(request, next_path=next_path, error="Не удалось отправить письмо. Проверьте настройки почты.")

    return _render_login(request, next_path=next_path, message=generic_message)


@router.get("/verify")
async def verify_login_link(
    request: Request,
    token: str,
    next: str = "/",
    db: AsyncSession = Depends(get_db),
):
    settings = request.app.state.settings
    result = await db.execute(
        select(AuthLoginToken).where(
            AuthLoginToken.token_hash == _token_hash(token),
            AuthLoginToken.used_at.is_(None),
        )
    )
    login_token = result.scalar_one_or_none()
    if not login_token or login_token.expires_at <= datetime.utcnow():
        return _render_login(request, next_path=next, error="Ссылка недействительна или уже истекла.")
    if not is_allowed_email(login_token.email, settings) or not settings.auth_secret:
        return _render_login(request, next_path=next, error="Ссылка недействительна.")

    login_token.used_at = datetime.utcnow()
    await db.commit()

    session_token = create_session_token(login_token.email, settings)
    response = RedirectResponse(safe_next_path(next), status_code=303)
    response.set_cookie(
        AUTH_COOKIE_NAME,
        session_token,
        max_age=max(1, settings.auth_session_days * 24 * 60 * 60),
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse("/auth/login", status_code=303)
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")
    return response
