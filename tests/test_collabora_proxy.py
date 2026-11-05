import asyncio
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import websockets
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocket
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.database import Base, get_db
from app.models import Document, DocumentItem, DocType, Project, Task, TaskAttachment, TaskStatus
from app.routers import collabora, documents, tasks, wopi
from app.routers.collabora import _collabora_upstream_headers
from app.storage import LocalStorage, get_storage


def test_collabora_websocket_headers_do_not_duplicate_host():
    settings = SimpleNamespace(armory_public_url="https://<your-domain>")

    assert _collabora_upstream_headers(settings) == {
        "Origin": "https://<your-domain>",
    }


@pytest.mark.parametrize("service_root", ["/collabora", ""])
def test_websocket_proxy_preserves_encoded_wopi_source(monkeypatch, service_root):
    settings = SimpleNamespace(
        collabora_enabled=True,
        collabora_internal_url="http://<service-host>",
        collabora_service_root=service_root,
        armory_public_url="https://<your-domain>",
    )
    app = FastAPI()
    app.include_router(collabora.router)
    app.dependency_overrides[get_settings] = lambda: settings
    targets = []
    connections = []

    def connect(target, **kwargs):
        targets.append(target)
        connections.append(kwargs)
        raise OSError("Остановка после проверки адреса подключения")

    monkeypatch.setattr(collabora.websockets, "connect", connect)
    encoded_source = "http%3A%2F%2Fservice%2Fwopi%2Ffiles%2Fdocument"
    suffix = f"/cool/{encoded_source}/ws?WOPISrc={encoded_source}&compat=/ws"
    with TestClient(app) as client:
        with client.websocket_connect(f"/collabora{suffix}") as websocket:
            assert websocket.receive()["type"] == "websocket.close"

    assert targets == [f"ws://<your-domain>{service_root}{suffix}"]
    assert connections == [{
        "additional_headers": {"Origin": "https://<your-domain>"},
        "host": "<service-host>",
        "port": 80,
        "proxy": None,
    }]


@pytest.mark.asyncio
@pytest.mark.parametrize("closing_side", ["client", "server"])
async def test_websocket_proxy_handshake_and_bidirectional_frames(closing_side):
    received = []
    sent = []
    incoming = asyncio.Queue()
    await incoming.put({"type": "websocket.connect"})
    await incoming.put({"type": "websocket.receive", "text": "load document"})
    encoded_source = "http%3A%2F%2Fservice%2Fwopi%2Ffiles%2Fdocument"
    raw_path = f"/collabora/cool/{encoded_source}/ws".encode("ascii")

    async def handler(connection):
        received.append(connection.request.headers.get_all("Host"))
        received.append(connection.request.headers["Origin"])
        received.append(connection.request.path)
        received.append(await connection.recv())
        await connection.send("status: ready")
        await connection.send(b"tile: document")
        if closing_side == "client":
            await connection.wait_closed()

    async def send(message):
        sent.append(message)
        if closing_side == "client" and message.get("bytes") == b"tile: document":
            await incoming.put({"type": "websocket.disconnect", "code": 1000})

    async with websockets.serve(handler, "localhost", 0) as server:
        host, port = server.sockets[0].getsockname()[:2]
        settings = SimpleNamespace(
            collabora_enabled=True,
            collabora_internal_url=f"http://[{host}]:{port}" if ":" in host else f"http://{host}:{port}",
            collabora_service_root="/collabora",
            armory_public_url="https://<your-domain>",
        )
        websocket = WebSocket(
            {"type": "websocket", "path": raw_path.decode(), "raw_path": raw_path,
             "query_string": b"compat=/ws", "headers": []},
            receive=incoming.get,
            send=send,
        )
        await asyncio.wait_for(collabora.proxy_collabora_ws(websocket, "", settings), timeout=5)

    assert received == [
        ["<your-domain>"],
        "https://<your-domain>",
        raw_path.decode() + "?compat=/ws",
        "load document",
    ]
    assert {"type": "websocket.send", "text": "status: ready"} in sent
    assert {"type": "websocket.send", "bytes": b"tile: document"} in sent


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["document", "task", "alexandrite"])
async def test_preview_api_and_wopi_resolve_the_same_file(tmp_path, monkeypatch, source):
    file_name = "проверка предпросмотра.DOCX"
    content = b"<document-content>"
    (tmp_path / file_name).write_bytes(content)
    settings = SimpleNamespace(
        collabora_enabled=True,
        collabora_internal_url="http://<service-host>",
        collabora_public_url="https://<your-domain>/collabora",
        collabora_wopi_internal_url="https://<your-domain>",
        collabora_wopi_secret="<test-secret-for-wopi-token-signing>",
        armory_public_url="https://<your-domain>",
        local_storage_path=str(tmp_path),
        alexandrite_vault_path=str(tmp_path),
    )

    async def discovery(_settings):
        return {"edit:docx": "http://<service-host>/browser/version/cool.html?"}

    monkeypatch.setattr(collabora, "_get_discovery_urls", discovery)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as db:
            db.add_all([
                Project(id=1, name="<project-name>"),
                Document(id=1, project_id=1, title="<document-title>"),
                DocumentItem(id=1, document_id=1, item_type=DocType.file,
                             file_name=file_name, file_path=file_name),
                TaskStatus(id=1, project_id=1, name="<status-name>"),
                Task(id=1, project_id=1, status_id=1, title="<task-title>"),
                TaskAttachment(id=1, task_id=1, attachment_type="file",
                               title="<attachment-title>", file_path=file_name),
            ])
            await db.commit()

        async def db_dependency():
            async with sessions() as db:
                yield db

        app = FastAPI()
        for router in (documents.router, tasks.router, collabora.router, wopi.router):
            app.include_router(router)
        app.dependency_overrides[get_db] = db_dependency
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_storage] = lambda: LocalStorage(str(tmp_path))
        endpoints = {
            "document": "/api/projects/1/documents/1/items/1/collabora",
            "task": "/api/projects/1/tasks/1/attachments/1/collabora",
            "alexandrite": "/api/alexandrite/collabora",
        }
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url=settings.armory_public_url) as client:
            response = await client.get(endpoints[source], params={"path": file_name})
            assert response.status_code == 200, response.text
            query = parse_qs(urlsplit(response.json()["url"]).query)
            wopi_src = query["WOPISrc"][0]
            assert wopi_src == response.json()["wopi_src"]
            token = {"access_token": query["access_token"][0]}
            metadata = await client.get(wopi_src, params=token)
            assert metadata.status_code == 200
            assert metadata.json()["BaseFileName"] == file_name
            assert metadata.json()["Size"] == len(content)
            download = await client.get(wopi_src + "/contents", params=token)
            assert download.status_code == 200
            assert download.content == content
            saved = await client.post(wopi_src + "/contents", params=token, content=content + b" updated")
            assert saved.status_code == 200
            assert (tmp_path / file_name).read_bytes() == content + b" updated"
    finally:
        await engine.dispose()
