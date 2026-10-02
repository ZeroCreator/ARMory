"""Проверяет запросы клиентов MCP перед передачей в потоковый HTTP-сервер."""

import hmac

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.agent_integration.oauth_provider import mcp_oauth_provider
from app.agent_integration.server import mcp_server
from app.config import get_settings


def _mcp_local_path(scope: Scope) -> str:
    path = scope.get("path", "")
    root_path = scope.get("root_path", "")
    if root_path and path.startswith(root_path):
        path = path[len(root_path):] or "/"
    elif path == "/mcp":
        path = "/"
    elif path.startswith("/mcp/"):
        path = path[len("/mcp"):]
    return path


def _is_oauth_protocol_path(scope: Scope) -> bool:
    path = _mcp_local_path(scope)
    return path in {
        "/authorize",
        "/token",
        "/register",
        "/revoke",
        "/.well-known/oauth-authorization-server",
        "/.well-known/oauth-protected-resource",
    }


class MCPAPIKeyMiddleware:
    """Сохраняет совместимость с ключом и передаёт OAuth-личность инструментам."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if _is_oauth_protocol_path(scope):
            await self.app(scope, receive, send)
            return

        settings = get_settings()
        headers = {
            name.decode("latin-1").lower(): value.decode("latin-1")
            for name, value in scope.get("headers", [])
        }
        authorization = headers.get("authorization", "")
        scheme, _, bearer_token = authorization.partition(" ")
        bearer_token = bearer_token.strip() if scheme.casefold() == "bearer" else ""

        if bearer_token:
            access_token = await mcp_oauth_provider.load_access_token(bearer_token)
            if access_token and access_token.user_email:
                supplied_key = headers.get("x-mcp-api-key", "")
                if settings.mcp_api_key and not hmac.compare_digest(supplied_key, settings.mcp_api_key):
                    response = JSONResponse(
                        status_code=401,
                        content={"detail": "Invalid or missing MCP API key"},
                    )
                    await response(scope, receive, send)
                    return

                state = scope.setdefault("state", {})
                if isinstance(state, dict):
                    state["user_email"] = access_token.user_email
        elif not authorization and settings.mcp_api_key:
            supplied_key = headers.get("x-mcp-api-key", "")
            if hmac.compare_digest(supplied_key, settings.mcp_api_key):
                scope = dict(scope)
                scope["headers"] = [
                    *scope.get("headers", []),
                    (b"authorization", f"Bearer {supplied_key}".encode("latin-1")),
                ]

        await self.app(scope, receive, send)


class MCPOAuthDiscoveryMiddleware:
    """Отдаёт OAuth-метаданные с поддержкой публичных клиентов."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and _mcp_local_path(scope) == "/.well-known/oauth-authorization-server":
            from app.routers.mcp_oauth import _authorization_server_metadata
            from starlette.responses import JSONResponse

            response = JSONResponse(
                content=_authorization_server_metadata(),
                headers={"Cache-Control": "public, max-age=3600"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


mcp_asgi_app: ASGIApp = MCPAPIKeyMiddleware(
    MCPOAuthDiscoveryMiddleware(mcp_server.streamable_http_app())
)
