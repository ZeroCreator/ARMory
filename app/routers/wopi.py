import base64
import json
import mimetypes
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from app.config import Settings, get_settings

router = APIRouter(tags=["wopi"])

# Расширения офисных документов, поддерживаемых Collabora Online
OFFICE_EXTENSIONS = {
    ".docx", ".doc",
    ".xlsx", ".xls",
    ".pptx", ".ppt",
    ".odt", ".ods", ".odp",
}


def _resolve_root(root: Optional[str], settings: Settings) -> Path:
    """Определить корневую папку Alexandrite."""
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


def _resolve_project_file_path(project_file_path: str, settings: Settings) -> Path:
    """Проверить, что путь файла проекта находится внутри локального хранилища."""
    base = Path(settings.local_storage_path).expanduser().resolve()
    try:
        file_path = (base / project_file_path).resolve()
        file_path.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project file path")
    return file_path


def _resolve_file_id_to_path(data: dict, settings: Settings) -> Path:
    """Определить путь к файлу из раскодированного file_id."""
    if "project_file_path" in data:
        return _resolve_project_file_path(data["project_file_path"], settings)
    root_path = _resolve_root(data.get("root") or None, settings)
    return _resolve_file_path(root_path, data["path"])


def encode_file_id(
    root: Optional[str] = None,
    path: Optional[str] = None,
    project_file_path: Optional[str] = None,
) -> str:
    """Закодировать root + path или project_file_path в file_id для WOPI."""
    if project_file_path:
        payload = json.dumps({"project_file_path": project_file_path}, ensure_ascii=False)
    else:
        payload = json.dumps({"root": root or "", "path": path or ""}, ensure_ascii=False)
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_file_id(file_id: str) -> dict:
    """Раскодировать file_id."""
    try:
        # Восстановить padding
        padding = 4 - len(file_id) % 4
        if padding != 4:
            file_id += "=" * padding
        decoded = base64.urlsafe_b64decode(file_id.encode("ascii"))
        return json.loads(decoded.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid file id") from e


def create_access_token(file_id: str, settings: Settings) -> str:
    """Создать JWT access token для WOPI."""
    if not settings.collabora_wopi_secret:
        raise HTTPException(status_code=500, detail="COLLABORA_WOPI_SECRET is not set")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": file_id,
        "iat": now,
        "exp": now + timedelta(hours=2),
    }
    return jwt.encode(payload, settings.collabora_wopi_secret, algorithm="HS256")


def verify_access_token(token: str, settings: Settings) -> str:
    """Проверить access token и вернуть file_id."""
    if not settings.collabora_wopi_secret:
        raise HTTPException(status_code=500, detail="COLLABORA_WOPI_SECRET is not set")
    try:
        payload = jwt.decode(token, settings.collabora_wopi_secret, algorithms=["HS256"])
        return payload["sub"]
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(status_code=403, detail="Access token expired") from e
    except Exception as e:
        raise HTTPException(status_code=403, detail="Invalid access token") from e


def _file_info(file_path: Path, settings: Settings) -> dict:
    """Сформировать CheckFileInfo ответ."""
    stat = file_path.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    mime, _ = mimetypes.guess_type(str(file_path))
    return {
        "BaseFileName": file_path.name,
        "OwnerId": "armory",
        "Size": stat.st_size,
        "Version": str(int(stat.st_mtime)),
        "UserId": "armory-user",
        "UserFriendlyName": "ARMory User",
        "UserCanWrite": True,
        "UserCanNotWriteRelative": True,
        "ReadOnly": False,
        "PostMessageOrigin": settings.collabora_public_url,
        "LastModifiedTime": mtime.isoformat(),
        "BreadcrumbDocName": file_path.name,
    }


@router.get("/wopi/files/{file_id}")
async def wopi_check_file_info(
    file_id: str,
    access_token: str = Query(...),
    settings: Settings = Depends(get_settings),
):
    """WOPI CheckFileInfo — метаданные файла."""
    data = _decode_file_id(verify_access_token(access_token, settings))
    file_path = _resolve_file_id_to_path(data, settings)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return _file_info(file_path, settings)


@router.get("/wopi/files/{file_id}/contents")
async def wopi_get_file(
    file_id: str,
    access_token: str = Query(...),
    settings: Settings = Depends(get_settings),
):
    """WOPI GetFile — содержимое файла."""
    data = _decode_file_id(verify_access_token(access_token, settings))
    file_path = _resolve_file_id_to_path(data, settings)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    mime, _ = mimetypes.guess_type(str(file_path))
    return FileResponse(
        file_path,
        media_type=mime or "application/octet-stream",
    )


@router.post("/wopi/files/{file_id}/contents")
async def wopi_put_file(
    request: Request,
    file_id: str,
    access_token: str = Query(...),
    settings: Settings = Depends(get_settings),
):
    """WOPI PutFile — сохранение файла."""
    data = _decode_file_id(verify_access_token(access_token, settings))
    file_path = _resolve_file_id_to_path(data, settings)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    body = await request.body()
    file_path.write_bytes(body)
    stat = file_path.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    return JSONResponse({
        "LastModifiedTime": mtime.isoformat(),
    })
