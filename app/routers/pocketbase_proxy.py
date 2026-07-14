"""Reverse proxy for the embedded PocketBase admin/API.

Mounted under /pocketbase/ so PocketBase is reachable through ARMory
without exposing an extra public port.
"""

import logging
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()

# Hop-by-hop headers must not be forwarded blindly.
_DROP_REQUEST_HEADERS = {
    "host",
    "accept-encoding",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}

_DROP_RESPONSE_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-length",
    "content-encoding",
}

# Reused async client pointing at the internal PocketBase container.
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=settings.pocketbase_internal_url,
            follow_redirects=False,
            timeout=httpx.Timeout(60.0),
        )
    return _client


def _rewrite_location(value: str) -> str:
    """Rewrite PocketBase-internal locations to stay under /pocketbase/."""
    public_prefix = settings.pocketbase_public_path.rstrip("/")
    internal_base = settings.pocketbase_internal_url.rstrip("/")

    parsed = urlparse(value)

    if parsed.scheme and parsed.netloc:
        # Absolute URL like http://pocketbase:8090/_/
        if value.startswith(internal_base):
            return public_prefix + value[len(internal_base):]
        return value

    if parsed.path.startswith("/"):
        # Relative URL like /_/
        return public_prefix + parsed.path

    # Relative without leading slash — rare, but keep as-is.
    return value


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def pocketbase_proxy(request: Request, path: str) -> Response:
    client = _get_client()

    target_path = "/" + path
    if request.query_params:
        target_path += "?" + str(request.query_params)

    headers = {
        name: value
        for name, value in request.headers.items()
        if name.lower() not in _DROP_REQUEST_HEADERS
    }

    body = await request.body()

    try:
        upstream = await client.request(
            method=request.method,
            url=target_path,
            headers=headers,
            content=body,
        )
    except httpx.RequestError as exc:
        logger.exception("PocketBase upstream request failed")
        return Response(f"PocketBase upstream error: {exc}", status_code=502)

    response_headers = {
        name: value
        for name, value in upstream.headers.items()
        if name.lower() not in _DROP_RESPONSE_HEADERS
    }

    if "location" in response_headers:
        response_headers["location"] = _rewrite_location(response_headers["location"])

    async def _stream():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()

    return StreamingResponse(
        _stream(),
        status_code=upstream.status_code,
        headers=response_headers,
    )
