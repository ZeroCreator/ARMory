import asyncio
import logging
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx
import websockets
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask
from starlette.websockets import WebSocket

from app.config import Settings, get_settings
from app.routers.wopi import (
    OFFICE_EXTENSIONS,
    create_access_token,
    encode_file_id,
    _resolve_root,
    _resolve_file_path,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["collabora"])

# Кэш discovery XML
_discovery_cache: Optional[dict] = None
_discovery_cache_time: Optional[datetime] = None


async def _get_discovery_urls(settings: Settings) -> dict:
    """Получить URL шаблоны из Collabora /hosting/discovery."""
    global _discovery_cache, _discovery_cache_time
    now = datetime.now(timezone.utc)
    if _discovery_cache and _discovery_cache_time and (now - _discovery_cache_time) < timedelta(minutes=5):
        return _discovery_cache

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            service_root = settings.collabora_service_root.strip("/")
            discovery_path = f"/{service_root}/hosting/discovery" if service_root else "/hosting/discovery"
            response = await client.get(f"{settings.collabora_internal_url}{discovery_path}")
            response.raise_for_status()
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Failed to connect to Collabora: {e}") from e

    try:
        root = ET.fromstring(response.text)
        urls = {}
        for app in root.findall(".//{http://schema.microsoft.com/office/online/2014/11/wopi-discovery}app"):
            for action in app.findall("{http://schema.microsoft.com/office/online/2014/11/wopi-discovery}action"):
                name = action.get("name", "")
                ext = action.get("ext", "")
                urlsrc = action.get("urlsrc", "")
                if name in ("edit", "view") and ext and urlsrc:
                    urls[f"{name}:{ext}"] = urlsrc
        # На случай, если namespace не указан
        if not urls:
            for app in root.findall(".//app"):
                for action in app.findall("action"):
                    name = action.get("name", "")
                    ext = action.get("ext", "")
                    urlsrc = action.get("urlsrc", "")
                    if name in ("edit", "view") and ext and urlsrc:
                        urls[f"{name}:{ext}"] = urlsrc
        _discovery_cache = urls
        _discovery_cache_time = now
        return urls
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to parse Collabora discovery: {e}") from e


@router.get("/api/alexandrite/collabora")
async def get_collabora_url(
    path: str = Query(...),
    root: Optional[str] = Query(None),
    settings: Settings = Depends(get_settings),
):
    """Вернуть URL iframe для редактирования файла в Collabora Online."""
    if not settings.collabora_enabled:
        raise HTTPException(status_code=503, detail="Collabora Online is not enabled")

    ext = Path(path).suffix.lower()
    if ext not in OFFICE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file type for Collabora")

    # Проверить, что файл существует и доступен
    root_path = _resolve_root(root, settings)
    file_path = _resolve_file_path(root_path, path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    # Сгенерировать WOPI file_id и URL iframe
    file_id = encode_file_id(root, path)
    iframe_url = await build_collabora_iframe_url(file_id, ext, settings)

    return JSONResponse({
        "url": iframe_url,
        "wopi_src": f"{settings.collabora_wopi_internal_url.rstrip('/')}/wopi/files/{file_id}",
    })


async def build_collabora_iframe_url(
    file_id: str,
    ext: str,
    settings: Settings,
) -> str:
    """Собрать URL iframe для Collabora Online по file_id и расширению файла."""
    discovery = await _get_discovery_urls(settings)
    ext_no_dot = ext.lstrip(".")
    urlsrc = discovery.get(f"edit:{ext_no_dot}")
    if not urlsrc:
        urlsrc = discovery.get(f"view:{ext_no_dot}")
    if not urlsrc:
        raise HTTPException(status_code=502, detail=f"Collabora does not support {ext}")

    token = create_access_token(file_id, settings)
    wopi_src = f"{settings.collabora_wopi_internal_url.rstrip('/')}/wopi/files/{file_id}"

    urlsrc_public = _make_collabora_public_url(urlsrc, settings)

    separator = "&" if "?" in urlsrc_public else "?"
    return (
        f"{urlsrc_public}{separator}WOPISrc={urllib.parse.quote(wopi_src, safe='')}"
        f"&access_token={urllib.parse.quote(token)}"
    )


def _make_collabora_public_url(urlsrc: str, settings: Settings) -> str:
    """Заменить внутренний scheme/netloc/path Collabora на публичный (через ARMory proxy)."""
    internal = urllib.parse.urlparse(settings.collabora_internal_url)
    public = urllib.parse.urlparse(settings.collabora_public_url)
    parsed = urllib.parse.urlparse(urlsrc)

    # Всегда использовать публичный scheme
    parsed = parsed._replace(scheme=public.scheme)

    # Если URL содержит внутренний netloc — заменить netloc на публичный
    if parsed.netloc == internal.netloc:
        parsed = parsed._replace(netloc=public.netloc)

    # Добавить префикс public_url path, если его ещё нет
    public_path = public.path.rstrip("/")
    if public_path and not parsed.path.startswith(public_path + "/"):
        parsed = parsed._replace(path=public_path + parsed.path)

    return urllib.parse.urlunparse(parsed)


@router.websocket("/collabora/cool/{path:path}")
async def proxy_collabora_ws(
    websocket: WebSocket,
    path: str,
    settings: Settings = Depends(get_settings),
):
    """WebSocket proxy для Collabora Online (/cool/...)."""
    if not settings.collabora_enabled:
        await websocket.close(code=1008)
        return

    await websocket.accept(
        subprotocol=websocket.headers.get("sec-websocket-protocol")
    )

    target_base = settings.collabora_internal_url.replace("http://", "ws://").replace("https://", "wss://")
    service_root = settings.collabora_service_root.strip("/")
    ws_path = f"{service_root}/cool/{path}" if service_root else f"cool/{path}"
    target_url = f"{target_base}/{ws_path}"
    if websocket.query_params:
        target_url += "?" + str(websocket.query_params)

    internal_url_parsed = urllib.parse.urlparse(settings.collabora_internal_url)
    internal_origin = f"{internal_url_parsed.scheme}://{internal_url_parsed.netloc}"

    client_subprotocol = websocket.headers.get("sec-websocket-protocol")
    connect_kwargs: dict = {
        "additional_headers": {
            "Host": internal_url_parsed.netloc,
            "Origin": internal_origin,
        },
    }
    if client_subprotocol:
        connect_kwargs["subprotocols"] = [client_subprotocol]

    ws = None
    try:
        async with websockets.connect(target_url, **connect_kwargs) as ws:
            async def client_to_server():
                while True:
                    try:
                        msg = await websocket.receive()
                    except Exception:
                        break
                    msg_type = msg.get("type")
                    if msg_type == "websocket.receive":
                        data = msg.get("text", msg.get("bytes"))
                        if isinstance(data, str):
                            await ws.send(data)
                        elif isinstance(data, bytes):
                            await ws.send(data)
                    elif msg_type == "websocket.disconnect":
                        break

            async def server_to_client():
                while True:
                    try:
                        data = await ws.recv()
                    except Exception:
                        break
                    if isinstance(data, str):
                        await websocket.send_text(data)
                    else:
                        await websocket.send_bytes(data)

            await asyncio.gather(client_to_server(), server_to_client())
    except Exception as exc:
        logger.exception("Collabora WebSocket proxy error")
    finally:
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass
        try:
            await websocket.close()
        except Exception:
            pass


@router.api_route(
    "/collabora/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS", "PATCH"],
)
async def proxy_collabora(
    request: Request,
    path: str,
    settings: Settings = Depends(get_settings),
):
    """Reverse proxy для статики и API Collabora Online."""
    if not settings.collabora_enabled:
        raise HTTPException(status_code=503, detail="Collabora Online is not enabled")

    service_root = settings.collabora_service_root.strip("/")
    proxy_path = f"{service_root}/{path}" if service_root else path
    target_url = f"{settings.collabora_internal_url}/{proxy_path}"
    if request.query_params:
        target_url += "?" + str(request.query_params)

    public_url_parsed = urllib.parse.urlparse(settings.armory_public_url)
    public_host = public_url_parsed.netloc
    headers = {}
    for key, value in request.headers.items():
        if key.lower() == "host":
            continue
        headers[key] = value
    headers["Host"] = public_host
    headers["X-Forwarded-Host"] = public_host
    headers["X-Forwarded-Proto"] = public_url_parsed.scheme or "https"
    headers["X-Forwarded-For"] = request.client.host if request.client else "127.0.0.1"

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=await request.body(),
                follow_redirects=False,
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Collabora proxy error: {e}") from e

    response_headers = dict(response.headers)
    response_headers.pop("content-encoding", None)
    response_headers.pop("transfer-encoding", None)
    response_headers.pop("content-length", None)

    async def stream():
        async for chunk in response.aiter_bytes():
            yield chunk

    return StreamingResponse(
        stream(),
        status_code=response.status_code,
        headers=response_headers,
        background=BackgroundTask(response.aclose),
    )
