"""Constrained Docker deployment jobs for ARMory extensions."""

import asyncio
import json
import os
import re
import shlex
import uuid
from urllib.parse import urlparse

import httpx

from app.extensions import install_manifest


_IMAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:@-]{0,254}$")
_JOBS: dict[str, dict] = {}


def get_job(job_id: str) -> dict | None:
    return _JOBS.get(job_id)


def validate_deployment(data: dict) -> dict:
    required = ("id", "name", "image", "container_port", "host_port", "public_url")
    if any(data.get(field) in (None, "") for field in required):
        raise ValueError("Заполните все обязательные поля")
    image = str(data["image"]).strip()
    extension_id = str(data["id"]).strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,62}", extension_id):
        raise ValueError("Некорректный идентификатор приложения")
    if not _IMAGE_RE.fullmatch(image):
        raise ValueError("Некорректное имя Docker-образа")
    try:
        container_port = int(data["container_port"])
        host_port = int(data["host_port"])
    except (TypeError, ValueError):
        raise ValueError("Порты должны быть числами") from None
    if not 1 <= container_port <= 65535 or not 1024 <= host_port <= 65535:
        raise ValueError("Порт приложения: 1–65535; локальный порт: 1024–65535")
    public_url = str(data["public_url"]).strip()
    parsed_url = urlparse(public_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError("Адрес для меню должен быть абсолютным HTTP(S)-адресом")
    return {
        **data,
        "id": extension_id,
        "public_url": public_url,
        "image": image,
        "container_port": container_port,
        "host_port": host_port,
        "health_path": "/" + str(data.get("health_path", "health")).strip().lstrip("/"),
    }


def start_deployment(data: dict) -> str:
    payload = validate_deployment(data)
    job_id = uuid.uuid4().hex
    _JOBS[job_id] = {"status": "queued", "logs": [], "event": asyncio.Event()}
    asyncio.create_task(_deploy(job_id, payload))
    return job_id


def _log(job: dict, message: str) -> None:
    job["logs"].append(message)
    job["event"].set()


async def _command(job: dict, arguments: list[str]) -> None:
    _log(job, "$ " + shlex.join(arguments))
    process = await asyncio.create_subprocess_exec(
        *arguments,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert process.stdout
    async for line in process.stdout:
        _log(job, line.decode(errors="replace").rstrip())
    code = await process.wait()
    if code:
        raise RuntimeError(f"Команда завершилась с кодом {code}")


async def _deploy(job_id: str, data: dict) -> None:
    job = _JOBS[job_id]
    job["status"] = "running"
    container_name = f"armory-extension-{data['id']}"
    try:
        _log(job, "Проверка параметров выполнена.")
        manager_url = os.getenv("EXTENSION_MANAGER_URL")
        if manager_url:
            _log(job, f"Передача операции внутреннему менеджеру: {manager_url}")
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", manager_url.rstrip("/") + "/deploy", json=data) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        item = json.loads(line)
                        if item.get("message"):
                            _log(job, item["message"])
                        if item.get("status") == "failed":
                            raise RuntimeError("Менеджер расширений не смог запустить приложение")
            install_manifest({
                "id": data["id"], "name": data["name"], "url": data["public_url"],
                "description": data.get("description", ""), "icon": data.get("icon", "bi-box"),
                "enabled": True, "image": data["image"], "container_name": container_name,
                "container_port": data["container_port"], "host_port": data["host_port"], "managed": True,
            })
            job["status"] = "complete"
            _log(job, "Готово: приложение развёрнуто и подключено к ARMory.")
            return
        inspect = await asyncio.create_subprocess_exec(
            "docker", "container", "inspect", container_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        if await inspect.wait() == 0:
            raise RuntimeError(f"Контейнер {container_name} уже существует")
        await _command(job, ["docker", "pull", data["image"]])
        await _command(job, [
            "docker", "run", "-d", "--name", container_name,
            "--restart", "unless-stopped",
            "--label", "armory.extension=true",
            "--label", f"armory.extension.id={data['id']}",
            "-p", f"127.0.0.1:{data['host_port']}:{data['container_port']}",
            data["image"],
        ])
        health_url = f"http://127.0.0.1:{data['host_port']}{data['health_path']}"
        _log(job, f"Проверка доступности: {health_url}")
        async with httpx.AsyncClient(timeout=3.0) as client:
            for attempt in range(1, 31):
                try:
                    response = await client.get(health_url)
                    if response.status_code < 500:
                        break
                except httpx.RequestError:
                    pass
                _log(job, f"Ожидание запуска: попытка {attempt}/30")
                await asyncio.sleep(1)
            else:
                await _command(job, ["docker", "stop", container_name])
                raise RuntimeError("Приложение не прошло проверку доступности за 30 секунд")
        install_manifest({
            "id": data["id"], "name": data["name"], "url": data["public_url"],
            "description": data.get("description", ""), "icon": data.get("icon", "bi-box"),
            "health_url": health_url, "enabled": True, "image": data["image"],
            "container_name": container_name, "container_port": data["container_port"],
            "host_port": data["host_port"], "managed": True,
        })
        job["status"] = "complete"
        _log(job, "Готово: приложение развёрнуто и подключено к ARMory.")
    except Exception as exc:
        job["status"] = "failed"
        _log(job, f"Ошибка: {exc}")
    finally:
        job["event"].set()
