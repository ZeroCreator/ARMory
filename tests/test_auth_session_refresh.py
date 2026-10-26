import time
from http.cookies import SimpleCookie
from types import SimpleNamespace

import httpx
import jwt
import pytest

from app.auth import AUTH_COOKIE_NAME
from app.main import RequireAuthMiddleware


def make_settings():
    return SimpleNamespace(
        auth_required=True,
        auth_mode="magic_link",
        auth_secret="<auth-secret-32-bytes-xxxxxxxxxxxx>",
        auth_allowed_emails="<authenticated-email>",
        auth_session_days=14,
        auth_cookie_secure=True,
        mcp_api_key=None,
        ai_assignee_email="<ai-assignee-email>",
    )


@pytest.mark.asyncio
async def test_authenticated_request_refreshes_magic_link_session_cookie():
    settings = make_settings()
    now = int(time.time())
    old_token = jwt.encode(
        {
            "iss": "armory",
            "sub": "<authenticated-email>",
            "iat": now - 60,
            "exp": now + 60,
            "typ": "session",
        },
        settings.auth_secret,
        algorithm="HS256",
    )

    async def app(scope, receive, send):
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json")],
        })
        await send({"type": "http.response.body", "body": b"{}"})

    wrapped_app = RequireAuthMiddleware(app, settings)
    transport = httpx.ASGITransport(app=wrapped_app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://<service-host>",
        cookies={AUTH_COOKIE_NAME: old_token},
    ) as client:
        response = await client.get("/api/tasks")

    refreshed_cookie = SimpleCookie(response.headers["set-cookie"])
    refreshed_token = refreshed_cookie[AUTH_COOKIE_NAME].value
    refreshed_payload = jwt.decode(
        refreshed_token,
        settings.auth_secret,
        algorithms=["HS256"],
        issuer="armory",
    )

    assert response.status_code == 200
    assert refreshed_token != old_token
    assert refreshed_payload["sub"] == "<authenticated-email>"
    assert refreshed_payload["exp"] > now + 60
    assert refreshed_cookie[AUTH_COOKIE_NAME]["httponly"] is True
    assert refreshed_cookie[AUTH_COOKIE_NAME]["secure"] is True


@pytest.mark.asyncio
async def test_auth_public_request_does_not_replace_login_cookie():
    settings = make_settings()

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    wrapped_app = RequireAuthMiddleware(app, settings)
    transport = httpx.ASGITransport(app=wrapped_app)
    async with httpx.AsyncClient(transport=transport, base_url="https://<service-host>") as client:
        response = await client.get("/auth/login")

    assert response.status_code == 200
    assert "set-cookie" not in response.headers


@pytest.mark.asyncio
async def test_service_request_does_not_receive_user_session_cookie():
    settings = make_settings()
    settings.mcp_api_key = "<mcp-api-key>"

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    wrapped_app = RequireAuthMiddleware(app, settings)
    transport = httpx.ASGITransport(app=wrapped_app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://<service-host>",
        headers={"Authorization": "Bearer <mcp-api-key>"},
    ) as client:
        response = await client.get("/api/tasks/1")

    assert response.status_code == 200
    assert "set-cookie" not in response.headers


@pytest.mark.asyncio
async def test_mcp_authorization_callback_receives_magic_link_session():
    settings = make_settings()
    now = int(time.time())
    session_token = jwt.encode(
        {
            "iss": "armory",
            "sub": "<authenticated-email>",
            "iat": now,
            "exp": now + 60,
            "typ": "session",
        },
        settings.auth_secret,
        algorithm="HS256",
    )
    captured_scope = {}

    async def app(scope, receive, send):
        captured_scope.update(scope)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    wrapped_app = RequireAuthMiddleware(app, settings)
    transport = httpx.ASGITransport(app=wrapped_app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://<service-host>",
        cookies={AUTH_COOKIE_NAME: session_token},
    ) as client:
        response = await client.get("/mcp/oauth/complete?request_id=<request-id>")

    assert response.status_code == 200
    assert captured_scope["state"]["user_email"] == "<authenticated-email>"
