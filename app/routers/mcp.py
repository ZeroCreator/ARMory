"""Проверяет запросы клиентов MCP перед передачей в потоковый HTTP-сервер."""

import hmac

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.agent_integration.server import mcp_server
from app.config import get_settings


class MCPAPIKeyMiddleware:
    """Проверяет отдельный ключ MCP перед обработкой HTTP-запроса."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        settings = get_settings()
        if not settings.mcp_api_key:
            response = JSONResponse(
                status_code=503,
                content={"detail": "MCP API key is not configured"},
            )
            await response(scope, receive, send)
            return

        headers = {
            name.decode("latin-1").lower(): value.decode("latin-1")
            for name, value in scope.get("headers", [])
        }
        supplied_key = headers.get("x-mcp-api-key", "")
        authorization = headers.get("authorization", "")
        scheme, _, bearer_key = authorization.partition(" ")
        if scheme.casefold() == "bearer" and bearer_key.strip():
            supplied_key = bearer_key.strip()

        if not hmac.compare_digest(supplied_key, settings.mcp_api_key):
            response = JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing MCP API key"},
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


mcp_asgi_app: ASGIApp = MCPAPIKeyMiddleware(mcp_server.streamable_http_app())
