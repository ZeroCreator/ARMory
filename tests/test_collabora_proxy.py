from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import get_settings
from app.routers import collabora
from app.routers.collabora import _collabora_upstream_headers


def test_collabora_websocket_uses_public_host_and_origin():
    settings = SimpleNamespace(armory_public_url="https://<your-domain>")

    assert _collabora_upstream_headers(settings) == {
        "Host": "<your-domain>",
        "Origin": "https://<your-domain>",
    }


@pytest.mark.parametrize("service_root", ["/collabora", ""])
def test_websocket_proxy_preserves_encoded_wopi_source(monkeypatch, service_root):
    settings = SimpleNamespace(
        collabora_enabled=True,
        collabora_internal_url="http://<service-host>:<port>",
        collabora_service_root=service_root,
        armory_public_url="https://<your-domain>",
    )
    app = FastAPI()
    app.include_router(collabora.router)
    app.dependency_overrides[get_settings] = lambda: settings
    targets = []

    def connect(target, **kwargs):
        targets.append(target)
        raise OSError("Остановка после проверки адреса подключения")

    monkeypatch.setattr(collabora.websockets, "connect", connect)
    encoded_source = "http%3A%2F%2Fservice%2Fwopi%2Ffiles%2Fdocument"
    suffix = f"/cool/{encoded_source}/ws?WOPISrc={encoded_source}&compat=/ws"
    with TestClient(app) as client:
        with client.websocket_connect(f"/collabora{suffix}") as websocket:
            assert websocket.receive()["type"] == "websocket.close"

    assert targets == [f"ws://<service-host>:<port>{service_root}{suffix}"]
