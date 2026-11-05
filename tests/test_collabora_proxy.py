from types import SimpleNamespace

from app.routers.collabora import _collabora_upstream_headers


def test_collabora_websocket_uses_public_host_and_origin():
    settings = SimpleNamespace(armory_public_url="https://<your-domain>")

    assert _collabora_upstream_headers(settings) == {
        "Host": "<your-domain>",
        "Origin": "https://<your-domain>",
    }
