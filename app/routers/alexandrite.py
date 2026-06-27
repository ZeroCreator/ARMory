import asyncio
import os
import base64
import mimetypes
import shutil
import tempfile
from pathlib import Path
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional

from app.config import get_settings, Settings
from app.yandex_disk import YandexDiskStorage

router = APIRouter(prefix="/api/alexandrite", tags=["alexandrite"])

# Текстовые расширения, которые можно отображать в редакторе
TEXT_EXTENSIONS = {
    ".md", ".txt", ".py", ".js", ".ts", ".html", ".css", ".json", ".yaml", ".yml",
    ".sql", ".java", ".go", ".rs", ".cpp", ".c", ".h", ".ini", ".cfg", ".log",
    ".sh", ".bash", ".zsh", ".ps1", ".xml", ".toml", ".env", ".example",
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".bmp", ".ico"}


def _resolve_root(root: Optional[str], settings: Settings) -> Path:
    """Определить корневую папку."""
    if root:
        path = Path(root).expanduser().resolve()
    else:
        path = Path(settings.alexandrite_vault_path).expanduser().resolve()
    if not path.exists():
        raise HTTPException(status_code=404, detail="Root directory not found")
    if not path.is_dir():
        raise HTTPException(status_code=400, detail="Root path is not a directory")
    return path


def _resolve_file_path(root_path: Path, path: str) -> Path:
    """Проверить, что путь файла находится внутри root, и вернуть его."""
    try:
        file_path = (root_path / path).resolve()
        file_path.relative_to(root_path.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file path")
    return file_path


def _is_hidden(name: str) -> bool:
    return name.startswith(".")


def _build_tree(path: Path, relative: str = "") -> List[dict]:
    """Рекурсивно построить дерево файлов и папок."""
    try:
        entries = list(path.iterdir())
    except PermissionError:
        return []

    dirs = []
    files = []
    for entry in entries:
        if _is_hidden(entry.name):
            continue
        rel = f"{relative}/{entry.name}" if relative else entry.name
        if entry.is_dir():
            children = _build_tree(entry, rel)
            dirs.append({
                "name": entry.name,
                "path": rel,
                "type": "directory",
                "children": children,
            })
        elif entry.is_file():
            files.append({
                "name": entry.name,
                "path": rel,
                "type": "file",
                "size": entry.stat().st_size,
            })

    dirs.sort(key=lambda x: x["name"].lower())
    files.sort(key=lambda x: x["name"].lower())
    return dirs + files


@router.get("/roots")
async def list_roots(settings: Settings = Depends(get_settings)):
    """Вернуть настроенные корневые папки. Пока одна."""
    default = Path(settings.alexandrite_vault_path).expanduser().resolve()
    return [
        {
            "name": default.name or "alexandrite",
            "path": str(default),
            "exists": default.exists() and default.is_dir(),
        }
    ]


@router.get("/browse")
async def browse_directories(
    path: Optional[str] = Query(None),
    settings: Settings = Depends(get_settings),
):
    """Вернуть список папок для файлового браузера.

    Если path не указан — начинаем с корня файловой системы (/),
    чтобы можно было выбрать любую папку на компьютере/сервере/контейнере.
    """
    if path:
        current = Path(path).expanduser().resolve()
    else:
        current = Path("/").resolve()

    if not current.exists():
        raise HTTPException(status_code=404, detail="Directory not found")
    if not current.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")

    try:
        entries = list(current.iterdir())
    except PermissionError:
        entries = []

    items = []
    for entry in entries:
        if _is_hidden(entry.name):
            continue
        if entry.is_dir():
            items.append({
                "name": entry.name,
                "path": str(entry.resolve()),
            })

    items.sort(key=lambda x: x["name"].lower())

    current_str = str(current)
    parent = str(current.parent.resolve()) if current_str != "/" else None
    return {
        "current": current_str,
        "parent": parent,
        "items": items,
    }


@router.get("/tree")
async def get_tree(
    root: Optional[str] = Query(None),
    settings: Settings = Depends(get_settings),
):
    root_path = _resolve_root(root, settings)
    tree = _build_tree(root_path)
    return {
        "root": str(root_path),
        "tree": tree,
    }


@router.get("/file")
async def get_file(
    path: str = Query(...),
    root: Optional[str] = Query(None),
    settings: Settings = Depends(get_settings),
):
    root_path = _resolve_root(root, settings)
    # Защита от path traversal: файл должен быть внутри root
    try:
        file_path = (root_path / path).resolve()
        file_path.relative_to(root_path)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file path")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    if not file_path.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file")

    ext = file_path.suffix.lower()
    mime, _ = mimetypes.guess_type(str(file_path))
    mime = mime or "application/octet-stream"

    if ext in IMAGE_EXTENSIONS:
        with open(file_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
        return {
            "type": "image",
            "mime_type": mime,
            "content": f"data:{mime};base64,{encoded}",
            "name": file_path.name,
        }

    if ext in TEXT_EXTENSIONS or mime and mime.startswith("text/"):
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return {
                "type": "binary",
                "mime_type": mime,
                "content": None,
                "name": file_path.name,
                "message": "Файл не является текстом",
            }
        return {
            "type": "text",
            "mime_type": mime,
            "content": content,
            "name": file_path.name,
        }

    return {
        "type": "binary",
        "mime_type": mime,
        "content": None,
        "name": file_path.name,
        "message": "Бинарный файл — предпросмотр не поддерживается",
    }


class FileCreate(BaseModel):
    path: str
    content: str = ""


class FileUpdate(BaseModel):
    path: str
    content: str


class FileRename(BaseModel):
    path: str
    new_name: str


class DirectoryCreate(BaseModel):
    path: str


class DirectoryRename(BaseModel):
    path: str
    new_name: str


EDITABLE_EXTENSIONS = {".md", ".txt"}


@router.post("/file")
async def create_file(
    data: FileCreate,
    root: Optional[str] = Query(None),
    settings: Settings = Depends(get_settings),
):
    """Создать новый .md или .txt файл внутри root."""
    root_path = _resolve_root(root, settings)
    file_path = _resolve_file_path(root_path, data.path)
    ext = file_path.suffix.lower()
    if ext not in EDITABLE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only .md and .txt files are allowed")
    if file_path.exists():
        raise HTTPException(status_code=400, detail="File already exists")

    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(data.content, encoding="utf-8")
    return {"status": "created", "path": str(file_path)}


@router.put("/file")
async def update_file(
    data: FileUpdate,
    root: Optional[str] = Query(None),
    settings: Settings = Depends(get_settings),
):
    """Обновить содержимое .md или .txt файла."""
    root_path = _resolve_root(root, settings)
    file_path = _resolve_file_path(root_path, data.path)
    ext = file_path.suffix.lower()
    if ext not in EDITABLE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only .md and .txt files can be edited")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    file_path.write_text(data.content, encoding="utf-8")
    return {"status": "updated", "path": str(file_path)}


@router.patch("/file")
async def rename_file(
    data: FileRename,
    root: Optional[str] = Query(None),
    settings: Settings = Depends(get_settings),
):
    """Переименовать файл внутри root."""
    root_path = _resolve_root(root, settings)
    file_path = _resolve_file_path(root_path, data.path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    new_name = data.new_name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="New name is required")
    if new_name in (".", "..") or "/" in new_name or "\\" in new_name:
        raise HTTPException(status_code=400, detail="Invalid file name")

    new_path = file_path.parent / new_name
    if new_path.exists():
        raise HTTPException(status_code=409, detail="File with this name already exists")

    file_path.rename(new_path)
    return {"status": "renamed", "path": str(new_path)}


@router.delete("/file")
async def delete_file(
    path: str = Query(...),
    root: Optional[str] = Query(None),
    settings: Settings = Depends(get_settings),
):
    """Удалить файл внутри root."""
    root_path = _resolve_root(root, settings)
    file_path = _resolve_file_path(root_path, path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    file_path.unlink()
    return {"status": "deleted"}


@router.post("/directory")
async def create_directory(
    data: DirectoryCreate,
    root: Optional[str] = Query(None),
    settings: Settings = Depends(get_settings),
):
    """Создать новую папку внутри root."""
    root_path = _resolve_root(root, settings)
    dir_path = _resolve_file_path(root_path, data.path)
    if dir_path.exists():
        raise HTTPException(status_code=400, detail="Directory already exists")

    dir_path.mkdir(parents=True, exist_ok=False)
    return {"status": "created", "path": str(dir_path)}


@router.patch("/directory")
async def rename_directory(
    data: DirectoryRename,
    root: Optional[str] = Query(None),
    settings: Settings = Depends(get_settings),
):
    """Переименовать папку внутри root."""
    root_path = _resolve_root(root, settings)
    dir_path = _resolve_file_path(root_path, data.path)
    if not dir_path.exists() or not dir_path.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")

    new_name = data.new_name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="New name is required")
    if new_name in (".", "..") or "/" in new_name or "\\" in new_name:
        raise HTTPException(status_code=400, detail="Invalid directory name")

    new_path = dir_path.parent / new_name
    if new_path.exists():
        raise HTTPException(status_code=409, detail="Directory with this name already exists")

    dir_path.rename(new_path)
    return {"status": "renamed", "path": str(new_path)}


@router.delete("/directory")
async def delete_directory(
    path: str = Query(...),
    root: Optional[str] = Query(None),
    settings: Settings = Depends(get_settings),
):
    """Удалить папку внутри root вместе с содержимым."""
    root_path = _resolve_root(root, settings)
    dir_path = _resolve_file_path(root_path, path)
    if not dir_path.exists() or not dir_path.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")

    shutil.rmtree(dir_path)
    return {"status": "deleted"}


# ═══════════════════════════════════════════════════
# Alexandrite: просмотр Яндекс.Диска (read-only)
# ═══════════════════════════════════════════════════

def _get_yandex_storage(settings: Settings) -> YandexDiskStorage:
    token = settings.yandex_disk_token
    if not token:
        raise HTTPException(status_code=503, detail="Яндекс.Диск не настроен")
    return YandexDiskStorage(token)


def _resolve_yandex_path(path: Optional[str], settings: Settings) -> str:
    """Проверяет и применяет ограничение просмотра Яндекс.Диска.

    Если задан ALEXANDRITE_YANDEX_ROOT_PATH, все пути должны быть внутри него.
    Возвращает нормализованный путь относительно Яндекс.Диска.
    """
    restricted_root = settings.alexandrite_yandex_root_path
    requested = path.strip("/") if path else ""

    if restricted_root:
        restricted_root = restricted_root.strip("/")
        if not requested:
            return restricted_root
        if requested != restricted_root and not requested.startswith(restricted_root + "/"):
            raise HTTPException(status_code=403, detail="Доступ за пределы разрешённой папки запрещён")
        return requested

    return requested


@router.get("/yandex/tree")
async def yandex_tree(
    path: Optional[str] = Query(None),
    settings: Settings = Depends(get_settings),
):
    """Возвращает содержимое одного уровня папки на Яндекс.Диске."""
    yandex = _get_yandex_storage(settings)

    remote_folder = _resolve_yandex_path(path, settings)
    try:
        items = await asyncio.to_thread(yandex.list_files, remote_folder)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ошибка Яндекс.Диска: {e}")

    tree = []
    for item in items:
        name = item.get("name", "")
        item_path = item.get("path", "")
        if item_path.startswith("disk:/"):
            item_path = item_path[6:]
        item_type = item.get("type", "file")
        tree.append({
            "name": name,
            "path": item_path,
            "type": "directory" if item_type == "dir" else "file",
            "size": item.get("size", 0) if item_type != "dir" else 0,
        })

    return {"root": remote_folder, "tree": tree}


@router.get("/yandex/file")
async def yandex_file(
    path: str = Query(...),
    settings: Settings = Depends(get_settings),
):
    """Скачивает файл с Яндекс.Диска и отдаёт его содержимое для просмотра."""
    yandex = _get_yandex_storage(settings)

    remote_path = _resolve_yandex_path(path, settings)
    ext = Path(remote_path).suffix.lower()
    ext = Path(remote_path).suffix.lower()
    mime, _ = mimetypes.guess_type(remote_path)
    mime = mime or "application/octet-stream"

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = tmp.name

    try:
        downloaded = await asyncio.to_thread(yandex.download_file, remote_path, tmp_path)
        if not downloaded:
            raise HTTPException(status_code=404, detail="Не удалось скачать файл с Яндекс.Диска")

        local_path = Path(tmp_path)

        if ext in IMAGE_EXTENSIONS:
            with open(local_path, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("utf-8")
            return {
                "type": "image",
                "mime_type": mime,
                "content": f"data:{mime};base64,{encoded}",
                "name": Path(remote_path).name,
            }

        if ext in TEXT_EXTENSIONS or (mime and mime.startswith("text/")):
            try:
                content = local_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return {
                    "type": "binary",
                    "mime_type": mime,
                    "content": None,
                    "name": Path(remote_path).name,
                    "message": "Файл не является текстом",
                }
            return {
                "type": "text",
                "mime_type": mime,
                "content": content,
                "name": Path(remote_path).name,
            }

        return {
            "type": "binary",
            "mime_type": mime,
            "content": None,
            "name": Path(remote_path).name,
            "message": "Бинарный файл — предпросмотр не поддерживается",
        }
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
