"""Local password and email magic-link authentication for ARMory."""

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
from sqlalchemy.exc import IntegrityError

from app.auth import (
    AUTH_COOKIE_NAME,
    create_session_token,
    hash_password,
    is_allowed_email,
    normalize_email,
    safe_next_path,
    verify_password,
)
from app.database import get_db
from app.models import AuthLoginToken, AuthUser


router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)

_RATE_LIMIT_WINDOW_SECONDS = 15 * 60
_RATE_LIMIT_MAX_ATTEMPTS = 5
_PASSWORD_MIN_LENGTH = 8
_request_attempts: dict[str, list[float]] = {}


def _render_login(
    request: Request,
    *,
    next_path: str = "/",
    message: str | None = None,
    error: str | None = None,
    email: str = "",
):
    return request.app.state.templates.TemplateResponse(
        "auth/login.html",
        {
            "request": request,
            "title": "Вход в ARMory",
            "next_path": safe_next_path(next_path),
            "message": message,
            "error": error,
            "email": email,
        },
    )


def _render_set_password(
    request: Request,
    *,
    email: str,
    next_path: str = "/",
    error: str | None = None,
):
    return request.app.state.templates.TemplateResponse(
        "auth/set_password.html",
        {
            "request": request,
            "title": "Установка пароля — ARMory",
            "email": email,
            "next_path": safe_next_path(next_path),
            "error": error,
            "password_min_length": _PASSWORD_MIN_LENGTH,
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


def _set_password_path(next_path: str) -> str:
    return "/auth/set-password?" + urlencode({"next": safe_next_path(next_path)})


def _login_path(next_path: str) -> str:
    return "/auth/login?" + urlencode({"next": _set_password_path(next_path)})


def _authenticated_email(request: Request) -> str:
    """Return an identity set by RequireAuthMiddleware, never the local fallback."""
    return normalize_email(getattr(request.state, "user_email", None))


def _set_session_cookie(response: RedirectResponse, email: str, settings) -> None:
    session_token = create_session_token(email, settings)
    response.set_cookie(
        AUTH_COOKIE_NAME,
        session_token,
        max_age=max(1, settings.auth_session_days * 24 * 60 * 60),
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


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
        f"Перейдите по ссылке, чтобы войти в ARMory. Ссылка действует {ttl_minutes} минут. "
        "Если пароль ещё не установлен, после перехода его можно будет задать:\n\n"
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
async def login_page(
    request: Request,
    next: str = "/",
    db: AsyncSession = Depends(get_db),
):
    settings = request.app.state.settings
    current_email = _authenticated_email(request)
    if current_email:
        if settings.auth_mode.casefold() == "magic_link":
            result = await db.execute(select(AuthUser).where(AuthUser.email == current_email))
            auth_user = result.scalar_one_or_none()
            if not auth_user or not auth_user.password_hash:
                return RedirectResponse(_set_password_path(next), status_code=303)
        return RedirectResponse(safe_next_path(next), status_code=303)
    return _render_login(request, next_path=next)


@router.post("/login")
async def login_with_password(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    db: AsyncSession = Depends(get_db),
):
    settings = request.app.state.settings
    next_path = safe_next_path(next)
    submitted = _submitted_email(email)
    if not submitted or not password:
        return _render_login(
            request,
            next_path=next_path,
            email=email,
            error="Введите email и пароль.",
        )

    if settings.auth_mode.casefold() != "magic_link" or not settings.auth_secret:
        logger.error("Cannot use local password login: authentication is not configured")
        return _render_login(
            request,
            next_path=next_path,
            email=submitted,
            error="Авторизация временно не настроена.",
        )

    password_rate_key = f"password:{_request_ip(request)}:{submitted}"
    if _rate_limited(password_rate_key):
        return _render_login(
            request,
            next_path=next_path,
            email=submitted,
            error="Неверный email или пароль. Если пароль ещё не установлен, запросите ссылку из почты.",
        )

    result = await db.execute(select(AuthUser).where(AuthUser.email == submitted))
    auth_user = result.scalar_one_or_none()
    if (
        not is_allowed_email(submitted, settings)
        or not auth_user
        or not await asyncio.to_thread(verify_password, password, auth_user.password_hash)
    ):
        return _render_login(
            request,
            next_path=next_path,
            email=submitted,
            error="Неверный email или пароль. Если пароль ещё не установлен, запросите ссылку из почты.",
        )

    _request_attempts.pop(password_rate_key, None)
    response = RedirectResponse(next_path, status_code=303)
    _set_session_cookie(response, submitted, settings)
    return response


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
        return _render_login(
            request,
            next_path=next_path,
            email=email,
            error="Введите корректный адрес электронной почты.",
        )

    generic_message = (
        "Если этот адрес добавлен в список доступа, письмо со ссылкой уже отправлено. "
        "Проверьте входящие и папку «Спам»."
    )
    rate_key = f"{_request_ip(request)}:{submitted}"
    if not is_allowed_email(submitted, settings) or _rate_limited(rate_key):
        return _render_login(request, next_path=next_path, email=submitted, message=generic_message)

    if not settings.auth_secret:
        logger.error("Cannot issue an ARMory login link: AUTH_SECRET is not configured")
        return _render_login(
            request,
            next_path=next_path,
            email=submitted,
            error="Авторизация временно не настроена.",
        )

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
        return _render_login(
            request,
            next_path=next_path,
            email=submitted,
            error="Не удалось подготовить ссылку входа.",
        )

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
        return _render_login(
            request,
            next_path=next_path,
            email=submitted,
            error="Не удалось отправить письмо. Проверьте настройки почты.",
        )

    return _render_login(request, next_path=next_path, email=submitted, message=generic_message)


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

    user_result = await db.execute(select(AuthUser).where(AuthUser.email == login_token.email))
    auth_user = user_result.scalar_one_or_none()
    redirect_path = safe_next_path(next) if auth_user and auth_user.password_hash else _set_password_path(next)
    response = RedirectResponse(redirect_path, status_code=303)
    _set_session_cookie(response, login_token.email, settings)
    return response


@router.get("/set-password")
async def set_password_page(
    request: Request,
    next: str = "/",
    db: AsyncSession = Depends(get_db),
):
    settings = request.app.state.settings
    email = _authenticated_email(request)
    if settings.auth_mode.casefold() != "magic_link" or not email or not is_allowed_email(email, settings):
        return RedirectResponse(_login_path(next), status_code=303)

    result = await db.execute(select(AuthUser).where(AuthUser.email == email))
    auth_user = result.scalar_one_or_none()
    if auth_user and auth_user.password_hash:
        return RedirectResponse(safe_next_path(next), status_code=303)
    return _render_set_password(request, email=email, next_path=next)


@router.post("/set-password")
async def set_password(
    request: Request,
    password: str = Form(...),
    password_confirmation: str = Form(...),
    next: str = Form("/"),
    db: AsyncSession = Depends(get_db),
):
    settings = request.app.state.settings
    next_path = safe_next_path(next)
    email = _authenticated_email(request)
    if settings.auth_mode.casefold() != "magic_link" or not email or not is_allowed_email(email, settings):
        return RedirectResponse(_login_path(next_path), status_code=303)

    if len(password) < _PASSWORD_MIN_LENGTH:
        return _render_set_password(
            request,
            email=email,
            next_path=next_path,
            error=f"Пароль должен содержать не менее {_PASSWORD_MIN_LENGTH} символов.",
        )
    if password != password_confirmation:
        return _render_set_password(
            request,
            email=email,
            next_path=next_path,
            error="Пароли не совпадают.",
        )

    result = await db.execute(select(AuthUser).where(AuthUser.email == email))
    auth_user = result.scalar_one_or_none()
    if auth_user and auth_user.password_hash:
        return _render_set_password(
            request,
            email=email,
            next_path=next_path,
            error="Пароль уже установлен. Войдите по email и паролю.",
        )

    password_hash = await asyncio.to_thread(hash_password, password)
    if auth_user:
        auth_user.password_hash = password_hash
    else:
        db.add(AuthUser(email=email, password_hash=password_hash))

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.exception("Failed to save an ARMory password")
        return _render_set_password(
            request,
            email=email,
            next_path=next_path,
            error="Не удалось сохранить пароль. Попробуйте ещё раз.",
        )

    return RedirectResponse(next_path, status_code=303)


@router.get("/logout")
async def logout():
    response = RedirectResponse("/auth/login", status_code=303)
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")
    return response
