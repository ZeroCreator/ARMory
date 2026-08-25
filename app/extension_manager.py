"""Internal, constrained Docker controller for extension deployment."""

import asyncio
import json
import os
import re
import urllib.request

import docker
from docker.errors import APIError, ImageNotFound, NotFound
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse


app = FastAPI(title="ARMory Extension Manager", docs_url=None, redoc_url=None)
_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
_IMAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:@-]{0,254}$")


def _validate(payload: dict) -> dict:
    extension_id = str(payload.get("id", "")).strip().lower()
    image = str(payload.get("image", "")).strip()
    if not _ID_RE.fullmatch(extension_id) or not _IMAGE_RE.fullmatch(image):
        raise ValueError("Некорректный идентификатор или Docker-образ")
    container_port = int(payload.get("container_port", 0))
    host_port = int(payload.get("host_port", 0))
    if not 1 <= container_port <= 65535 or not 1024 <= host_port <= 65535:
        raise ValueError("Некорректные порты")
    return {**payload, "id": extension_id, "image": image, "container_port": container_port, "host_port": host_port}


def _deploy(payload: dict, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue) -> None:
    def emit(message: str) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, {"message": message})

    client = docker.from_env()
    name = f"armory-extension-{payload['id']}"
    try:
        network_name = os.getenv("EXTENSIONS_DOCKER_NETWORK")
        if not network_name:
            manager = client.containers.get(os.environ["HOSTNAME"])
            networks = manager.attrs["NetworkSettings"]["Networks"]
            network_name = next(iter(networks))
        try:
            client.containers.get(name)
            raise RuntimeError(f"Контейнер {name} уже существует")
        except NotFound:
            pass
        emit(f"$ docker pull {payload['image']}")
        for item in client.api.pull(payload["image"], stream=True, decode=True):
            text = item.get("status") or item.get("error")
            if text:
                detail = item.get("progress", "")
                emit(f"{text}{' ' + detail if detail else ''}")
            if item.get("error"):
                raise RuntimeError(item["error"])
        emit(f"$ docker run -d --name {name} --restart unless-stopped -p 127.0.0.1:{payload['host_port']}:{payload['container_port']} {payload['image']}")
        container = client.containers.run(
            payload["image"], detach=True, name=name, restart_policy={"Name": "unless-stopped"},
            ports={f"{payload['container_port']}/tcp": ("127.0.0.1", payload["host_port"])},
            labels={"armory.extension": "true", "armory.extension.id": payload["id"]},
            network=network_name,
        )
        health_path = "/" + str(payload.get("health_path", "health")).strip().lstrip("/")
        health_url = f"http://{name}:{payload['container_port']}{health_path}"
        emit(f"Проверка доступности: {health_url}")
        for attempt in range(1, 31):
            try:
                with urllib.request.urlopen(health_url, timeout=3) as response:
                    if response.status < 500:
                        queue_status = "complete"
                        break
            except Exception:
                pass
            emit(f"Ожидание запуска: попытка {attempt}/30")
            import time
            time.sleep(1)
        else:
            container.stop(timeout=10)
            raise RuntimeError("Приложение не прошло проверку доступности за 30 секунд")
        emit("Контейнер запущен и прошёл проверку доступности.")
        loop.call_soon_threadsafe(queue.put_nowait, {"status": queue_status})
    except (APIError, ImageNotFound, RuntimeError, ValueError) as exc:
        emit(f"Ошибка Docker: {exc}")
        loop.call_soon_threadsafe(queue.put_nowait, {"status": "failed"})
    finally:
        client.close()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/deploy")
async def deploy(request: Request):
    try:
        payload = _validate(await request.json())
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    asyncio.create_task(asyncio.to_thread(_deploy, payload, loop, queue))

    async def stream():
        while True:
            item = await queue.get()
            yield json.dumps(item, ensure_ascii=False) + "\n"
            if "status" in item:
                return

    return StreamingResponse(stream(), media_type="application/x-ndjson")
