"""Маршруты обнаружения OAuth и возврата браузерной авторизации MCP."""

from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.agent_integration.oauth_provider import mcp_oauth_provider
from app.auth import normalize_email


router = APIRouter(tags=["mcp-oauth"])


def _protected_resource_metadata() -> dict:
    return {
        "resource": mcp_oauth_provider.resource_url,
        "authorization_servers": [mcp_oauth_provider.issuer_url],
        "scopes_supported": ["kanban"],
        "bearer_methods_supported": ["header"],
    }


def _authorization_server_metadata() -> dict:
    issuer = mcp_oauth_provider.issuer_url
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/token",
        "registration_endpoint": f"{issuer}/register",
        "scopes_supported": ["kanban"],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none"],
        "code_challenge_methods_supported": ["S256"],
    }


@router.get("/.well-known/oauth-protected-resource")
@router.get("/.well-known/oauth-protected-resource/mcp")
async def protected_resource_metadata():
    return JSONResponse(
        content=_protected_resource_metadata(),
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/.well-known/oauth-authorization-server/mcp")
async def authorization_server_metadata():
    return JSONResponse(
        content=_authorization_server_metadata(),
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/mcp/oauth/complete")
async def complete_authorization(request: Request, request_id: str):
    email = normalize_email(getattr(request.state, "user_email", None))
    if not email:
        next_path = request.url.path
        if request.url.query:
            next_path = f"{next_path}?{request.url.query}"
        login_url = f"/auth/login?{urlencode({'next': next_path})}"
        return RedirectResponse(login_url, status_code=303)

    redirect_url = await mcp_oauth_provider.complete_authorization(request_id, email)
    if redirect_url is None:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_request"},
            headers={"Cache-Control": "no-store"},
        )

    return RedirectResponse(
        redirect_url,
        status_code=302,
        headers={"Cache-Control": "no-store"},
    )
