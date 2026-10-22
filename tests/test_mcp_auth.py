from types import SimpleNamespace

import pytest

from app.routers import mcp as mcp_router


@pytest.mark.asyncio
async def test_mcp_api_key_replaces_expired_oauth_token(monkeypatch):
    settings = SimpleNamespace(mcp_api_key="<mcp-api-key>")
    captured_scope = {}

    async def load_access_token(token):
        return None

    async def app(scope, receive, send):
        captured_scope.update(scope)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    monkeypatch.setattr(mcp_router, "get_settings", lambda: settings)
    monkeypatch.setattr(mcp_router.mcp_oauth_provider, "load_access_token", load_access_token)
    middleware = mcp_router.MCPAPIKeyMiddleware(app)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [
            (b"authorization", b"Bearer <expired-oauth-token>"),
            (b"x-mcp-api-key", b"<mcp-api-key>"),
        ],
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        return None

    await middleware(scope, receive, send)

    headers = dict(captured_scope["headers"])
    assert headers[b"authorization"] == b"Bearer <mcp-api-key>"
    assert b"x-mcp-api-key" in headers
