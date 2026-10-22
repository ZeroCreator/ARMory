"""Проверяет запросы клиентов MCP перед передачей в потоковый HTTP-сервер."""

import asyncio
import hmac
import time

from mcp.server.streamable_http import MCP_SESSION_ID_HEADER
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.agent_integration.oauth_provider import mcp_oauth_provider
from app.agent_integration.server import mcp_server
from app.config import get_settings


_MCP_SESSION_TTL_SECONDS = 60 * 60
_MCP_SESSION_CLEANUP_INTERVAL_SECONDS = 5 * 60


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

        access_token = await mcp_oauth_provider.load_access_token(bearer_token) if bearer_token else None
        supplied_key = headers.get("x-mcp-api-key", "")
        api_key_valid = bool(
            settings.mcp_api_key
            and hmac.compare_digest(supplied_key, settings.mcp_api_key)
        )
        if access_token and access_token.user_email:
            if settings.mcp_api_key and not api_key_valid:
                response = JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing MCP API key"},
                )
                await response(scope, receive, send)
                return

            state = scope.setdefault("state", {})
            if isinstance(state, dict):
                state["user_email"] = access_token.user_email
        elif api_key_valid:
            scope = dict(scope)
            scope["headers"] = [
                (name, value)
                for name, value in scope.get("headers", [])
                if name.lower() != b"authorization"
            ]
            scope["headers"].append(
                (b"authorization", f"Bearer {supplied_key}".encode("latin-1")),
            )

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


class MCPSessionCleanupMiddleware:
    """Ограничивает срок жизни неактивных stateful MCP-сессий."""

    def __init__(self, app: ASGIApp, session_manager: StreamableHTTPSessionManager):
        self.app = app
        self.session_manager = session_manager
        self._last_seen: dict[str, float] = {}
        self._cleanup_lock = asyncio.Lock()

    @staticmethod
    def _request_session_id(scope: Scope) -> str | None:
        for name, value in scope.get("headers", []):
            if name.lower() == MCP_SESSION_ID_HEADER.encode("latin-1"):
                return value.decode("latin-1")
        return None

    async def cleanup(self) -> None:
        """Удаляет завершённые и давно неактивные MCP-сессии."""
        async with self._cleanup_lock:
            instances = getattr(self.session_manager, "_server_instances", None)
            if not isinstance(instances, dict):
                return

            now = time.monotonic()
            for session_id in tuple(self._last_seen):
                if session_id not in instances:
                    self._last_seen.pop(session_id, None)
            stale_sessions = []
            for session_id, transport in list(instances.items()):
                last_seen = self._last_seen.get(session_id, now)
                if (
                    getattr(transport, "is_terminated", False)
                    or now - last_seen >= _MCP_SESSION_TTL_SECONDS
                ):
                    stale_sessions.append((session_id, transport))

            for session_id, transport in stale_sessions:
                if not getattr(transport, "is_terminated", False):
                    await transport.terminate()
                if instances.get(session_id) is transport:
                    instances.pop(session_id, None)
                self._last_seen.pop(session_id, None)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        session_id = self._request_session_id(scope)
        if session_id:
            self._last_seen[session_id] = time.monotonic()
        response_session_id = None

        async def send_with_session_tracking(message):
            nonlocal response_session_id
            if message["type"] == "http.response.start":
                for name, value in message.get("headers", []):
                    if name.lower() == MCP_SESSION_ID_HEADER.encode("latin-1"):
                        response_session_id = value.decode("latin-1")
                        break
            await send(message)

        try:
            await self.app(scope, receive, send_with_session_tracking)
        finally:
            if response_session_id:
                self._last_seen[response_session_id] = time.monotonic()
            await self.cleanup()


mcp_session_cleanup = MCPSessionCleanupMiddleware(
    mcp_server.streamable_http_app(),
    mcp_server.session_manager,
)
mcp_asgi_app: ASGIApp = MCPAPIKeyMiddleware(
    MCPOAuthDiscoveryMiddleware(mcp_session_cleanup)
)


async def cleanup_mcp_sessions_loop() -> None:
    """Периодически очищает MCP-сессии без новых HTTP-запросов."""
    while True:
        await asyncio.sleep(_MCP_SESSION_CLEANUP_INTERVAL_SECONDS)
        await mcp_session_cleanup.cleanup()
