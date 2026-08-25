"""Registry of independently deployed applications connected to ARMory."""

import json
import os
import re
import tempfile
from pathlib import Path
from threading import RLock
from urllib.parse import urlparse


REGISTRY_PATH = Path(os.getenv("EXTENSIONS_REGISTRY_PATH", "data/extensions.json"))
_LOCK = RLock()
_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,62}$")

def _read_registry() -> dict[str, dict]:
    if not REGISTRY_PATH.exists():
        return {}
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_registry(data: dict[str, dict]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        dir=REGISTRY_PATH.parent,
        prefix=".extensions-",
        suffix=".json",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as temporary_file:
            json.dump(data, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.write("\n")
        os.replace(temporary_name, REGISTRY_PATH)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def list_extensions() -> list[dict]:
    with _LOCK:
        return sorted(_read_registry().values(), key=lambda item: item["name"].casefold())


def enabled_extensions() -> list[dict]:
    return [extension for extension in list_extensions() if extension.get("enabled")]


def is_enabled(extension_id: str) -> bool:
    return any(
        extension["id"] == extension_id and extension.get("enabled")
        for extension in list_extensions()
    )


def set_enabled(extension_id: str, enabled: bool) -> dict:
    extensions = {item["id"]: item for item in list_extensions()}
    if extension_id not in extensions:
        raise KeyError(extension_id)
    with _LOCK:
        saved = _read_registry()
        saved.setdefault(extension_id, {})["enabled"] = enabled
        _write_registry(saved)
    return next(item for item in list_extensions() if item["id"] == extension_id)


def install_manifest(manifest: dict) -> dict:
    required = {"id", "name", "url"}
    if not required.issubset(manifest):
        raise ValueError("Манифест должен содержать id, name и url")
    extension_id = str(manifest["id"]).strip().lower()
    if not _ID_RE.fullmatch(extension_id):
        raise ValueError("id должен содержать 2–63 строчные латинские буквы, цифры или дефисы")
    if "enabled" in manifest and not isinstance(manifest["enabled"], bool):
        raise ValueError("enabled должен быть логическим значением")
    url = str(manifest["url"]).strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("url должен быть абсолютным HTTP(S)-адресом")
    extension = {
        "id": extension_id,
        "name": str(manifest["name"]).strip()[:100],
        "description": str(manifest.get("description", "")).strip()[:500],
        "url": url,
        "health_url": str(manifest.get("health_url", "")).strip()[:1000] or None,
        "icon": str(manifest.get("icon", "bi-box")).strip()[:100],
        "enabled": bool(manifest.get("enabled", False)),
    }
    for field in ("image", "container_name", "container_port", "host_port", "managed"):
        if field in manifest:
            extension[field] = manifest[field]
    if not extension["name"]:
        raise ValueError("name не может быть пустым")
    with _LOCK:
        saved = _read_registry()
        saved[extension_id] = extension
        _write_registry(saved)
    return extension
