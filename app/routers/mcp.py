"""HTTP MCP endpoint для Kimi Code CLI.

Принимает JSON-RPC запросы по HTTP и делегирует обработку mcp_logic.
Защищён статичным API-ключом (MCP_API_KEY), потому что endpoint
пропускается мимо oauth2-proxy через OAUTH2_PROXY_SKIP_AUTH_ROUTES.
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.config import get_settings
from mcp.mcp_logic import handle_message

router = APIRouter(prefix="/mcp", tags=["mcp"])


def _verify_mcp_key(request: Request):
    settings = get_settings()
    key = settings.mcp_api_key
    if not key:
        return

    header_key = request.headers.get("x-mcp-api-key")
    auth_header = request.headers.get("authorization", "")
    bearer_key = auth_header.removeprefix("Bearer ").strip() if auth_header.startswith("Bearer ") else ""

    if header_key != key and bearer_key != key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing MCP API key",
        )


@router.post("", dependencies=[Depends(_verify_mcp_key)])
async def mcp_endpoint(request: Request):
    """JSON-RPC endpoint для MCP over HTTP."""
    msg = await request.json()
    host, port = request.scope.get("server", ("localhost", 80))
    base_url = f"http://127.0.0.1:{port}"
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, handle_message, msg, base_url)
    id_ = msg.get("id")

    if result is None:
        # Notification — no response required.
        return Response(status_code=204)

    response = {"jsonrpc": "2.0", "id": id_}
    if isinstance(result, dict) and "error" in result:
        response["error"] = result["error"]
    else:
        response["result"] = result

    return JSONResponse(content=response)


@router.get("", dependencies=[Depends(_verify_mcp_key)])
async def mcp_get():
    """Заглушка для GET-запросов (некоторые MCP клиенты делают probe)."""
    return JSONResponse(content={"ok": True})
