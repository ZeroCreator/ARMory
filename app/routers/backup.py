import asyncio
import json
import os
import re
import shutil
import sqlite3
import tarfile
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from threading import Lock
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models import (
    CalendarEvent,
    Document,
    DocumentItem,
    Project,
    Section,
    SidebarBlock,
    SidebarLink,
    Task,
    TaskStatus,
    DocType,
)
from app.yandex_disk import YandexDiskStorage

router = APIRouter(prefix="/api/backup", tags=["backup"])

settings = get_settings()

_YANDEX_BASE = settings.yandex_disk_path.strip("/")
REMOTE_DB = f"{_YANDEX_BASE}/armory.db"
REMOTE_UPLOADS = f"{_YANDEX_BASE}/uploads"
REMOTE_BACKUPS = settings.yandex_disk_backups_path.strip("/")
REMOTE_ALEXANDRITE = settings.yandex_disk_alexandrite_path.strip("/")
REMOTE_ALEXANDRITE_BACKUPS = f"{REMOTE_BACKUPS}/alexandrite"
LOCAL_BACKUPS = Path("data/backups")
SYNC_STATE_PATH = Path("data/sync_state.json")
_BACKUP_TARGETS = {"local", "yandex", "both"}
_BACKUP_SOURCES = {"local", "yandex"}
_SYNC_STATE_KEYS = {"armory_last_sync_at", "alexandrite_last_sync_at"}
_sync_state_lock = Lock()

# Хранилище фоновых задач экспорта/архивирования (job_id -> status)
_backup_jobs: Dict[str, dict] = {}
_alexandrite_export_jobs: Dict[str, dict] = {}
_BACKUP_JOB_RETENTION = timedelta(hours=24)
_MAX_BACKUP_JOBS = 128
_TERMINAL_BACKUP_STATUSES = {"completed", "error"}


def _cleanup_old_backup_jobs() -> None:
    """Удаляет задачи старше 24 часов, чтобы не текла память."""
    cutoff = datetime.now() - _BACKUP_JOB_RETENTION
    for store in (_backup_jobs, _alexandrite_export_jobs):
        expired = [
            job_id for job_id, job in store.items()
            if _job_created_at(job) < cutoff
        ]
        for job_id in expired:
            store.pop(job_id, None)

        removable = sorted(
            (
                (_job_created_at(job), job_id)
                for job_id, job in store.items()
                if job.get("status") in _TERMINAL_BACKUP_STATUSES
            ),
        )
        for _, job_id in removable[: max(0, len(store) - _MAX_BACKUP_JOBS)]:
            store.pop(job_id, None)


def _job_created_at(job: dict) -> datetime:
    value = job.get("created_at")
    try:
        created_at = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return datetime.min
    if created_at.tzinfo:
        return created_at.astimezone(timezone.utc).replace(tzinfo=None)
    return created_at


def _get_yandex() -> YandexDiskStorage | None:
    token = settings.yandex_disk_token
    if not token:
        return None
    return YandexDiskStorage(token, _YANDEX_BASE)


def _validate_archive_name(name: str) -> str:
    """Проверяет имя архива и исключает выход за пределы каталога бэкапов."""
    if (
        not isinstance(name, str)
        or Path(name).name != name
        or not re.fullmatch(r"armory_backup_\d{8}_\d{6}\.tar\.gz", name)
    ):
        raise HTTPException(status_code=400, detail="Некорректное имя архива")
    return name


def _validate_alexandrite_archive_name(name: str) -> str:
    """Проверяет имя архива Alexandrite и исключает выход из каталога."""
    if (
        not isinstance(name, str)
        or Path(name).name != name
        or not re.fullmatch(r"alexandrite_backup_\d{8}_\d{6}\.tar\.gz", name)
    ):
        raise HTTPException(status_code=400, detail="Некорректное имя архива")
    return name


def _validate_backup_source(source: str) -> str:
    """Проверяет источник архива."""
    if not isinstance(source, str) or source not in _BACKUP_SOURCES:
        raise HTTPException(status_code=400, detail="Некорректный источник архива")
    return source


def _local_archive_path(name: str) -> Path:
    """Возвращает путь к локальному архиву."""
    return LOCAL_BACKUPS / _validate_archive_name(name)


def _local_alexandrite_archive_path(name: str) -> Path:
    """Возвращает путь к локальному архиву Alexandrite."""
    return LOCAL_BACKUPS / _validate_alexandrite_archive_name(name)


def _archive_sort_key(item: dict) -> tuple[int, float, str]:
    """Возвращает ключ сортировки архива от ранней даты к поздней."""
    modified_at = item.get("modified_at")
    if isinstance(modified_at, str) and modified_at:
        try:
            modified = datetime.fromisoformat(modified_at.replace("Z", "+00:00"))
            if modified.tzinfo is None:
                modified = modified.replace(tzinfo=timezone.utc)
            return (0, modified.timestamp(), str(item.get("name", "")))
        except (TypeError, ValueError, OverflowError):
            pass
    return (1, 0, str(item.get("name", "")))


def _cleanup_archive_download(temp_dir: Path) -> None:
    """Удаляет временный каталог после отправки архива пользователю."""
    shutil.rmtree(temp_dir, ignore_errors=True)


def _read_sync_state() -> dict[str, str]:
    """Читает сохранённые даты завершённых синхронизаций."""
    if not SYNC_STATE_PATH.is_file():
        return {}
    try:
        value = json.loads(SYNC_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(value, dict):
        return {}
    return {
        key: item
        for key, item in value.items()
        if key in _SYNC_STATE_KEYS and isinstance(item, str)
    }


def _write_sync_state(state: dict[str, str]) -> None:
    """Атомарно сохраняет даты завершённых синхронизаций."""
    SYNC_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = SYNC_STATE_PATH.with_suffix(".tmp")
    try:
        temporary_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_path, SYNC_STATE_PATH)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _record_sync(key: str) -> str:
    """Записывает время успешного завершения синхронизации."""
    if key not in _SYNC_STATE_KEYS:
        raise ValueError("Неизвестный тип синхронизации")
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with _sync_state_lock:
        state = _read_sync_state()
        state[key] = timestamp
        _write_sync_state(state)
    return timestamp


def _sync_state_payload() -> dict[str, str | None]:
    """Возвращает даты синхронизаций для API и интерфейса."""
    with _sync_state_lock:
        state = _read_sync_state()
    return {
        "last_sync_at": state.get("armory_last_sync_at"),
        "last_sync": _format_dt(state.get("armory_last_sync_at", "")) or None,
        "alexandrite_last_sync_at": state.get("alexandrite_last_sync_at"),
        "alexandrite_last_sync": _format_dt(state.get("alexandrite_last_sync_at", "")) or None,
    }


async def _gather_stats(session: AsyncSession) -> dict:
    async def count_rows(model) -> int:
        return int(await session.scalar(select(func.count()).select_from(model)) or 0)

    item_type_counts_result = await session.execute(
        select(DocumentItem.item_type, func.count())
        .group_by(DocumentItem.item_type)
    )
    item_type_counts = {
        item_type.value if isinstance(item_type, DocType) else item_type: count
        for item_type, count in item_type_counts_result
    }
    sidebar_link_notes = int(
        await session.scalar(
            select(func.count())
            .select_from(SidebarLink)
            .where(
                SidebarLink.note.is_not(None),
                func.trim(SidebarLink.note) != "",
            )
        )
        or 0
    )

    total_size = 0
    uploads_path = Path(settings.local_storage_path).resolve()
    file_paths = await session.stream_scalars(
        select(DocumentItem.file_path).where(
            DocumentItem.item_type == DocType.file,
            DocumentItem.file_path.is_not(None),
        )
    )
    try:
        async for file_path in file_paths:
            fp = uploads_path / file_path
            if fp.exists():
                total_size += fp.stat().st_size
    finally:
        await file_paths.close()

    return {
        "projects": await count_rows(Project),
        "sections": await count_rows(Section),
        "documents": await count_rows(Document),
        "links": item_type_counts.get("link", 0),
        "files": item_type_counts.get("file", 0),
        "notes": item_type_counts.get("note", 0),
        "sidebar_blocks": await count_rows(SidebarBlock),
        "sidebar_links": await count_rows(SidebarLink),
        "sidebar_link_notes": sidebar_link_notes,
        "calendar_events": await count_rows(CalendarEvent),
        "task_statuses": await count_rows(TaskStatus),
        "tasks": await count_rows(Task),
        "total_files_size": total_size,
    }


# ── хелперы для загрузки/скачивания с Яндекс.Диска ────────────────────────

def _upload_uploads(
    yandex: YandexDiskStorage,
    uploads_src: Path,
    remote_uploads: str,
    job_id: str | None = None,
) -> dict:
    """Синхронная загрузка всех файлов из uploads. Возвращает {uploaded, skipped}."""
    uploaded = 0
    skipped = 0
    if not uploads_src.exists():
        print("[BACKUP] uploads_src does not exist")
        return {"uploaded": 0, "skipped": 0}

    files = list(uploads_src.rglob("*"))
    file_list = [f for f in files if f.is_file()]
    total_size = sum(f.stat().st_size for f in file_list)
    processed_size = 0

    if job_id and job_id in _backup_jobs:
        _backup_jobs[job_id]["total"] = len(file_list)
        _backup_jobs[job_id]["total_size"] = total_size
        _backup_jobs[job_id]["status"] = "running"

    for idx, local_file in enumerate(file_list, start=1):
        rel = local_file.relative_to(uploads_src)
        remote_path = f"{remote_uploads}/{rel.as_posix()}"
        file_size = local_file.stat().st_size

        if job_id and job_id in _backup_jobs:
            _backup_jobs[job_id]["current_file"] = rel.as_posix()
            _backup_jobs[job_id]["processed"] = idx - 1
            _backup_jobs[job_id]["processed_size"] = processed_size

        def _progress(done, total):
            if job_id and job_id in _backup_jobs:
                _backup_jobs[job_id]["processed_size"] = processed_size + done
                _backup_jobs[job_id]["current_file_size"] = total

        ok = yandex.upload_file_with_progress(str(local_file), remote_path, progress_callback=_progress)
        if ok:
            uploaded += 1
            processed_size += file_size
        else:
            print(f"[BACKUP] FAILED {rel}")

        if job_id and job_id in _backup_jobs:
            _backup_jobs[job_id]["uploaded"] = uploaded
            _backup_jobs[job_id]["processed"] = idx
            _backup_jobs[job_id]["processed_size"] = processed_size

    return {"uploaded": uploaded, "skipped": skipped, "total_size": total_size}


def _download_uploads(yandex: YandexDiskStorage, remote_uploads: str, uploads_dst: Path) -> dict:
    """Синхронное скачивание всех файлов из remote uploads. Возвращает {downloaded, skipped}."""
    downloaded = 0
    skipped = 0

    remote_files = yandex.list_all_files(remote_uploads)

    remote_rels = set()
    for f in remote_files:
        rel = f["rel"]
        remote_rels.add(rel)
        local_file = uploads_dst / rel
        need_download = True
        if local_file.exists():
            if local_file.stat().st_size == f["size"]:
                need_download = False
                skipped += 1
        if need_download:
            remote_path = f["path"]
            if remote_path.startswith("disk:/"):
                remote_path = remote_path[6:]
            yandex.download_file(remote_path, str(local_file))
            downloaded += 1

    return {"downloaded": downloaded, "skipped": skipped}


# ── хелперы восстановления ──────────────────────────────────────────────────

def _read_sqlite_dump(db_path: Path) -> Dict[str, Any]:
    """Читает sqlite файл и возвращает dump всех таблиц."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    tables = [
        "projects",
        "sections",
        "documents",
        "document_items",
        "sidebar_blocks",
        "sidebar_links",
        "calendar_events",
        "task_statuses",
        "tasks",
    ]

    dump = {"version": 1}
    for table in tables:
        cur.execute(f"SELECT * FROM {table}")
        rows = cur.fetchall()
        dump[table] = [dict(row) for row in rows]

    conn.close()
    return dump


async def _restore_dump(dump: dict, session: AsyncSession) -> dict:
    """Очищает БД и вставляет данные из dump."""
    await session.execute(delete(CalendarEvent))
    await session.execute(delete(SidebarLink))
    await session.execute(delete(SidebarBlock))
    await session.execute(delete(DocumentItem))
    await session.execute(delete(Document))
    await session.execute(delete(Section))
    await session.execute(delete(Task))
    await session.execute(delete(TaskStatus))
    await session.execute(delete(Project))
    await session.commit()

    tables_order = [
        (Project, "projects"),
        (TaskStatus, "task_statuses"),
        (Task, "tasks"),
        (Section, "sections"),
        (Document, "documents"),
        (DocumentItem, "document_items"),
        (SidebarBlock, "sidebar_blocks"),
        (SidebarLink, "sidebar_links"),
        (CalendarEvent, "calendar_events"),
    ]

    stats = {}
    for model, key in tables_order:
        rows = dump.get(key, [])
        if rows:
            # datetime поля приходят строками из sqlite
            prepared = []
            for row in rows:
                out = {}
                for col in model.__table__.columns:
                    val = row.get(col.name)
                    if val is None:
                        out[col.name] = None
                    elif col.name in ("created_at", "updated_at", "start_date", "end_date", "due_date") and isinstance(val, str):
                        out[col.name] = datetime.fromisoformat(val)
                    elif col.name == "item_type" and isinstance(val, str):
                        out[col.name] = val
                    else:
                        out[col.name] = val
                prepared.append(out)
            await session.execute(insert(model), prepared)
        stats[f"{key}_restored"] = len(rows)

    await session.commit()

    for model, key in tables_order:
        seq_name = model.__tablename__
        try:
            await session.execute(
                text(
                    f"UPDATE sqlite_sequence SET seq=(SELECT COALESCE(MAX(id),0) FROM {seq_name}) WHERE name='{seq_name}'"
                )
            )
        except Exception:
            pass
    await session.commit()

    return stats


def _format_dt(iso_string: str) -> str:
    """Конвертирует ISO-строку UTC в локальное время из settings.timezone."""
    if not iso_string:
        return ""
    try:
        dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        import zoneinfo
        tz = zoneinfo.ZoneInfo(settings.timezone)
        local_dt = dt.astimezone(tz)
        return local_dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return iso_string


# ── хелперы архивов ──────────────────────────────────────────────────

_ARCHIVE_COMPRESSION_LEVEL = 1
_ARCHIVE_DISK_RESERVE_BYTES = 512 * 1024 * 1024

def _local_auto_backup(db_path: Path, uploads_src: Path) -> Path:
    """Создаёт локальную резервную копию перед destructive операциями."""
    backup_dir = Path("data/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    auto_dir = backup_dir / f"auto_{ts}"
    auto_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_path, auto_dir / "armory.db")
    if uploads_src.exists():
        shutil.copytree(uploads_src, auto_dir / "uploads", dirs_exist_ok=True)
    return auto_dir


def _iter_regular_files(root: Path):
    """Потоково перебирает обычные файлы, не переходя по символическим ссылкам."""
    if not root.exists():
        return

    for directory, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_dir = Path(directory)
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if not (current_dir / dirname).is_symlink()
        ]
        for filename in filenames:
            file_path = current_dir / filename
            if not file_path.is_symlink() and file_path.is_file():
                yield file_path


def _iter_backup_files(db_path: Path, uploads_src: Path):
    """Потоково перебирает файлы основного архива и их имена внутри tar."""
    if db_path.is_symlink() or not db_path.is_file():
        raise RuntimeError(f"Файл базы данных не найден: {db_path}")
    yield db_path, "armory.db"

    for file_path in _iter_regular_files(uploads_src):
        arcname = "uploads/" + file_path.relative_to(uploads_src).as_posix()
        yield file_path, arcname


def _ensure_archive_disk_space(dest_path: Path, total_size: int) -> None:
    """Проверяет запас места перед созданием локального архива."""
    free_size = shutil.disk_usage(dest_path.parent).free
    required_size = total_size + _ARCHIVE_DISK_RESERVE_BYTES
    if free_size < required_size:
        raise RuntimeError(
            "Недостаточно свободного места для создания архива: "
            f"нужно не менее {required_size} байт, доступно {free_size}"
        )


def _create_tarball(db_path: Path, uploads_src: Path, dest_path: Path, job_id: str | None = None) -> None:
    """Создаёт tar.gz с БД и uploads, обновляя прогресс в задаче."""
    total_files = 0
    total_size = 0
    for file_path, _ in _iter_backup_files(db_path, uploads_src):
        total_files += 1
        total_size += file_path.stat().st_size
    _ensure_archive_disk_space(dest_path, total_size)
    processed_size = 0

    if job_id and job_id in _backup_jobs:
        _backup_jobs[job_id]["total"] = total_files
        _backup_jobs[job_id]["total_size"] = total_size
        _backup_jobs[job_id]["status"] = "packing"

    with tarfile.open(dest_path, "w:gz", compresslevel=_ARCHIVE_COMPRESSION_LEVEL) as tar:
        for idx, (file_path, arcname) in enumerate(_iter_backup_files(db_path, uploads_src), start=1):
            tar.add(file_path, arcname=arcname, recursive=False)
            processed_size += file_path.stat().st_size
            if job_id and job_id in _backup_jobs:
                _backup_jobs[job_id]["processed"] = idx
                _backup_jobs[job_id]["processed_size"] = processed_size
                _backup_jobs[job_id]["current_file"] = arcname

    if job_id and job_id in _backup_jobs:
        _backup_jobs[job_id]["status"] = "running"


def _extract_tarball(tar_path: Path, db_dest: Path, uploads_dest: Path) -> None:
    """Распаковывает tar.gz в указанные пути без выхода из uploads."""
    uploads_root = uploads_dest.resolve()
    with tarfile.open(tar_path, "r:gz") as tar:
        for member in tar.getmembers():
            if member.name == "armory.db":
                if not member.isfile():
                    continue
                extracted = tar.extractfile(member)
                if extracted:
                    with db_dest.open("wb") as output:
                        shutil.copyfileobj(extracted, output, length=1024 * 1024)
            elif member.name.startswith("uploads/"):
                rel = Path(member.name[len("uploads/"):])
                if (
                    not member.isfile()
                    or rel.is_absolute()
                    or ".." in rel.parts
                ):
                    raise RuntimeError(f"Некорректный путь в архиве: {member.name}")
                out_path = (uploads_root / rel).resolve()
                if uploads_root not in out_path.parents:
                    raise RuntimeError(f"Некорректный путь в архиве: {member.name}")
                extracted = tar.extractfile(member)
                if extracted:
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    with out_path.open("wb") as output:
                        shutil.copyfileobj(extracted, output, length=1024 * 1024)


def _list_local_backups() -> list:
    """Возвращает список архивов из локального каталога бэкапов."""
    if not LOCAL_BACKUPS.exists():
        return []

    backups = []
    for archive_path in LOCAL_BACKUPS.glob("armory_backup_*.tar.gz"):
        if not archive_path.is_file() or not re.fullmatch(
            r"armory_backup_\d{8}_\d{6}\.tar\.gz",
            archive_path.name,
        ):
            continue
        modified_at = datetime.fromtimestamp(
            archive_path.stat().st_mtime,
            tz=timezone.utc,
        ).isoformat()
        backups.append({
            "name": archive_path.name,
            "size": archive_path.stat().st_size,
            "modified": _format_dt(modified_at),
            "modified_at": modified_at,
            "source": "local",
        })
    return sorted(backups, key=_archive_sort_key)


def _list_backups(yandex: YandexDiskStorage) -> list:
    """Возвращает список архивов на Яндекс.Диске в папке бэкапов."""
    items = yandex.list_files(REMOTE_BACKUPS)
    backups = []
    for item in items:
        name = item.get("name", "")
        if item.get("type") == "file" and re.fullmatch(
            r"armory_backup_\d{8}_\d{6}\.tar\.gz",
            name,
        ):
            modified_at = item.get("modified") or ""
            backups.append({
                "name": name,
                "size": item.get("size", 0),
                "modified": _format_dt(modified_at),
                "modified_at": modified_at,
                "source": "yandex",
            })
    return sorted(backups, key=_archive_sort_key)


# ── хелперы Alexandrite ──────────────────────────────────────────────

def _is_hidden_path(path: Path, root: Path) -> bool:
    """Проверяет, что путь или любая его родительская папка скрытая (начинается с точки)."""
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False
    return any(part.startswith(".") for part in rel.parts)


def _gather_alexandrite_stats(local_path: Path) -> dict:
    """Собирает статистику по локальной папке Alexandrite (без скрытых файлов)."""
    files_count = 0
    dirs_count = 0
    total_size = 0
    if local_path.exists():
        for entry in local_path.rglob("*"):
            if _is_hidden_path(entry, local_path):
                continue
            if entry.is_file():
                files_count += 1
                total_size += entry.stat().st_size
            elif entry.is_dir():
                dirs_count += 1
    return {
        "files": files_count,
        "directories": dirs_count,
        "total_size": total_size,
        "path": str(local_path),
    }


def _upload_alexandrite(
    yandex: YandexDiskStorage,
    local_src: Path,
    remote_base: str,
    job_id: str | None = None,
) -> dict:
    """Загружает файлы из папки Alexandrite на Я.Диск, пропуская скрытые.

    Если передан job_id, обновляет статус выполнения в _alexandrite_export_jobs.
    """
    uploaded = 0
    failed = 0
    if not local_src.exists():
        return {"uploaded": 0, "failed": 0}

    files = [f for f in local_src.rglob("*") if f.is_file() and not _is_hidden_path(f, local_src)]
    total_size = sum(f.stat().st_size for f in files)
    processed_size = 0

    if job_id and job_id in _alexandrite_export_jobs:
        _alexandrite_export_jobs[job_id]["total"] = len(files)
        _alexandrite_export_jobs[job_id]["total_size"] = total_size
        _alexandrite_export_jobs[job_id]["status"] = "running"

    for idx, local_file in enumerate(files, start=1):
        rel = local_file.relative_to(local_src)
        remote_path = f"{remote_base}/{rel.as_posix()}"
        file_size = local_file.stat().st_size

        if job_id and job_id in _alexandrite_export_jobs:
            _alexandrite_export_jobs[job_id]["current_file"] = rel.as_posix()
            _alexandrite_export_jobs[job_id]["processed"] = idx - 1
            _alexandrite_export_jobs[job_id]["processed_size"] = processed_size

        def _progress(done, total):
            if job_id and job_id in _alexandrite_export_jobs:
                _alexandrite_export_jobs[job_id]["processed_size"] = processed_size + done
                _alexandrite_export_jobs[job_id]["current_file_size"] = total

        if yandex.upload_file_with_progress(str(local_file), remote_path, progress_callback=_progress):
            uploaded += 1
            processed_size += file_size
        else:
            failed += 1
            print(f"[ALEXANDRITE BACKUP] FAILED {rel}")

        if job_id and job_id in _alexandrite_export_jobs:
            _alexandrite_export_jobs[job_id]["uploaded"] = uploaded
            _alexandrite_export_jobs[job_id]["failed"] = failed
            _alexandrite_export_jobs[job_id]["processed"] = idx
            _alexandrite_export_jobs[job_id]["processed_size"] = processed_size

    return {"uploaded": uploaded, "failed": failed}


def _download_alexandrite(yandex: YandexDiskStorage, remote_base: str, local_dst: Path) -> dict:
    """Скачивает файлы папки Alexandrite с Я.Диска, пропуская скрытые."""
    downloaded = 0
    skipped = 0

    remote_files = yandex.list_all_files(remote_base)
    for f in remote_files:
        rel = f["rel"]
        if "/." in rel or rel.startswith("."):
            continue
        local_file = local_dst / rel
        need_download = True
        if local_file.exists():
            if local_file.stat().st_size == f["size"]:
                need_download = False
                skipped += 1
        if need_download:
            remote_path = f["path"]
            if remote_path.startswith("disk:/"):
                remote_path = remote_path[6:]
            yandex.download_file(remote_path, str(local_file))
            downloaded += 1

    return {"downloaded": downloaded, "skipped": skipped}


def _create_alexandrite_tarball(local_src: Path, dest_path: Path) -> None:
    """Создаёт tar.gz только с содержимым папки Alexandrite, без скрытых файлов."""
    files = (
        file_path
        for file_path in _iter_regular_files(local_src)
        if not _is_hidden_path(file_path, local_src)
    )
    total_size = sum(file_path.stat().st_size for file_path in files)
    _ensure_archive_disk_space(dest_path, total_size)

    with tarfile.open(dest_path, "w:gz", compresslevel=_ARCHIVE_COMPRESSION_LEVEL) as tar:
        for file_path in _iter_regular_files(local_src):
            if not _is_hidden_path(file_path, local_src):
                arcname = "alexandrite/" + file_path.relative_to(local_src).as_posix()
                tar.add(file_path, arcname=arcname, recursive=False)


def _extract_alexandrite_tarball(tar_path: Path, local_dst: Path) -> None:
    """Распаковывает tar.gz в папку Alexandrite."""
    with tarfile.open(tar_path, "r:gz") as tar:
        for member in tar.getmembers():
            if member.name.startswith("alexandrite/"):
                extracted = tar.extractfile(member)
                if extracted:
                    rel = member.name[len("alexandrite/"):]
                    out_path = local_dst / rel
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    with out_path.open("wb") as output:
                        shutil.copyfileobj(extracted, output, length=1024 * 1024)


def _local_auto_backup_alexandrite(local_src: Path) -> Path:
    """Локальная резервная копия папки Alexandrite перед destructive операциями."""
    backup_dir = Path("data/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    auto_dir = backup_dir / f"auto_{ts}"
    auto_dir.mkdir(parents=True, exist_ok=True)
    if local_src.exists():
        shutil.copytree(local_src, auto_dir / "alexandrite", dirs_exist_ok=True)
    return auto_dir


def _list_alexandrite_backups(yandex: YandexDiskStorage) -> list:
    """Возвращает список архивов Alexandrite на Я.Диске."""
    items = yandex.list_files(REMOTE_ALEXANDRITE_BACKUPS)
    backups = []
    for item in items:
        name = item.get("name", "")
        if item.get("type") == "file" and re.fullmatch(
            r"alexandrite_backup_\d{8}_\d{6}\.tar\.gz",
            name,
        ):
            modified_at = item.get("modified") or ""
            backups.append({
                "name": name,
                "size": item.get("size", 0),
                "modified": _format_dt(modified_at),
                "modified_at": modified_at,
                "source": "yandex",
            })
    return sorted(backups, key=_archive_sort_key)


def _list_local_alexandrite_backups() -> list:
    """Возвращает список локальных архивов Alexandrite."""
    if not LOCAL_BACKUPS.exists():
        return []

    backups = []
    for archive_path in LOCAL_BACKUPS.glob("alexandrite_backup_*.tar.gz"):
        if not archive_path.is_file() or not re.fullmatch(
            r"alexandrite_backup_\d{8}_\d{6}\.tar\.gz",
            archive_path.name,
        ):
            continue
        modified_at = datetime.fromtimestamp(
            archive_path.stat().st_mtime,
            tz=timezone.utc,
        ).isoformat()
        backups.append({
            "name": archive_path.name,
            "size": archive_path.stat().st_size,
            "modified": _format_dt(modified_at),
            "modified_at": modified_at,
            "source": "local",
        })
    return sorted(backups, key=_archive_sort_key)


# ── эндпоинты ────────────────────────────────────────────────────────


@router.get("/stats")
async def backup_stats():
    _cleanup_old_backup_jobs()
    yandex = _get_yandex()
    yandex_status = {"connected": False, "info": "Токен не настроен"}
    if yandex:
        conn = await asyncio.to_thread(yandex.test_connection)
        yandex_status = {
            "connected": conn["ok"],
            "info": conn.get("info", ""),
            "used": conn.get("used", ""),
            "total": conn.get("total", ""),
        }

    async with AsyncSessionLocal() as session:
        stats = await _gather_stats(session)

    return {"local": stats, "yandex": yandex_status, "sync": _sync_state_payload()}


@router.post("/sync-export")
async def sync_export():
    yandex = _get_yandex()
    if not yandex:
        raise HTTPException(status_code=503, detail="Яндекс.Диск не настроен")

    _cleanup_old_backup_jobs()

    db_path = Path(settings.database_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")).resolve()
    uploads_src = Path(settings.local_storage_path).resolve()

    job_id = str(uuid.uuid4())
    _backup_jobs[job_id] = {
        "status": "starting",
        "total": 0,
        "uploaded": 0,
        "skipped": 0,
        "processed": 0,
        "total_size": 0,
        "processed_size": 0,
        "current_file": "",
        "created_at": datetime.now().isoformat(),
    }
    asyncio.create_task(_run_sync_export_async(yandex, db_path, uploads_src, job_id))
    return {"job_id": job_id}


async def _run_sync_export_async(
    yandex: YandexDiskStorage, db_path: Path, uploads_src: Path, job_id: str
) -> None:
    """Фоновая задача экспорта основных данных с обновлением прогресса."""
    try:
        auto_backup = await asyncio.to_thread(_local_auto_backup, db_path, uploads_src)

        if job_id in _backup_jobs:
            _backup_jobs[job_id]["status"] = "running"
            _backup_jobs[job_id]["current_file"] = "armory.db"

        await asyncio.to_thread(yandex.create_folder, _YANDEX_BASE)
        await asyncio.to_thread(yandex.create_folder, REMOTE_UPLOADS)

        db_uploaded = await asyncio.to_thread(yandex.upload_file, str(db_path), REMOTE_DB)
        if not db_uploaded:
            raise RuntimeError("Не удалось загрузить armory.db на Яндекс.Диск")

        upload_stats = await asyncio.to_thread(_upload_uploads, yandex, uploads_src, REMOTE_UPLOADS, job_id)

        async with AsyncSessionLocal() as session:
            stats = await _gather_stats(session)

        last_sync_at = await asyncio.to_thread(_record_sync, "armory_last_sync_at")
        if job_id in _backup_jobs:
            _backup_jobs[job_id]["status"] = "completed"
            _backup_jobs[job_id]["last_sync_at"] = last_sync_at
            _backup_jobs[job_id]["last_sync"] = _format_dt(last_sync_at)
            _backup_jobs[job_id]["stats"] = {
                **{k: v for k, v in stats.items()},
                "db_uploaded": db_uploaded,
                "files_uploaded": upload_stats["uploaded"],
                "files_skipped": upload_stats["skipped"],
                "auto_backup": str(auto_backup),
                "last_sync_at": last_sync_at,
                "last_sync": _format_dt(last_sync_at),
            }
            _backup_jobs[job_id]["current_file"] = ""
    except Exception as e:
        if job_id in _backup_jobs:
            _backup_jobs[job_id]["status"] = "error"
            _backup_jobs[job_id]["error"] = str(e)
            _backup_jobs[job_id]["current_file"] = ""


@router.post("/sync-import")
async def sync_import():
    yandex = _get_yandex()
    if not yandex:
        raise HTTPException(status_code=503, detail="Яндекс.Диск не настроен")

    db_path = Path(settings.database_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")).resolve()
    uploads_src = Path(settings.local_storage_path).resolve()

    # Автоматический локальный бэкап перед destructive операцией
    auto_backup = await asyncio.to_thread(_local_auto_backup, db_path, uploads_src)

    temp_dir = Path(os.environ.get("TMPDIR", "/tmp")) / f"armory_sync_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Скачиваем БД
        local_db = temp_dir / "armory.db"
        db_downloaded = await asyncio.to_thread(yandex.download_file, REMOTE_DB, str(local_db))
        if not db_downloaded:
            raise HTTPException(status_code=502, detail="Не удалось скачать armory.db с Яндекс.Диска. Возможно, синхронизация ещё не выполнялась.")

        # Читаем sqlite dump
        dump = await asyncio.to_thread(_read_sqlite_dump, local_db)

        # Восстанавливаем БД
        async with AsyncSessionLocal() as session:
            db_stats = await _restore_dump(dump, session)

        # Скачиваем uploads
        uploads_dst = Path(settings.local_storage_path).resolve()
        uploads_dst.mkdir(parents=True, exist_ok=True)
        file_stats = await asyncio.to_thread(_download_uploads, yandex, REMOTE_UPLOADS, uploads_dst)
        last_sync_at = await asyncio.to_thread(_record_sync, "armory_last_sync_at")

        return {
            "success": True,
            "stats": {
                **db_stats,
                "files_downloaded": file_stats["downloaded"],
                "files_skipped": file_stats["skipped"],
                "auto_backup": str(auto_backup),
                "last_sync_at": last_sync_at,
                "last_sync": _format_dt(last_sync_at),
            },
        }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ── эндпоинты архивов ────────────────────────────────────────────────

@router.get("/archives")
async def list_archives():
    yandex = _get_yandex()
    backups = await asyncio.to_thread(_list_local_backups)
    if yandex:
        backups.extend(await asyncio.to_thread(_list_backups, yandex))
    backups.sort(key=_archive_sort_key)
    return {"archives": backups}


@router.post("/create")
async def create_archive(payload: dict | None = None):
    payload = payload or {}
    yandex = _get_yandex()
    target = payload.get("backup_target")
    if target is None:
        target = "both" if yandex else "local"
    if not isinstance(target, str) or target not in _BACKUP_TARGETS:
        raise HTTPException(status_code=400, detail="Некорректное место сохранения бэкапа")
    if target in {"yandex", "both"} and not yandex:
        raise HTTPException(status_code=503, detail="Яндекс.Диск не настроен")

    _cleanup_old_backup_jobs()
    active_job = next(
        (
            job
            for job in _backup_jobs.values()
            if job.get("status") in {"starting", "packing", "running", "uploading"}
            and job.get("archive_name")
        ),
        None,
    )
    if active_job:
        raise HTTPException(status_code=409, detail="Создание резервной копии уже выполняется")

    db_path = Path(settings.database_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")).resolve()
    uploads_src = Path(settings.local_storage_path).resolve()

    job_id = str(uuid.uuid4())
    archive_name = f"armory_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tar.gz"
    if target in {"local", "both"}:
        LOCAL_BACKUPS.mkdir(parents=True, exist_ok=True)
        archive_dir = LOCAL_BACKUPS
    else:
        archive_dir = Path(os.environ.get("TMPDIR", "/tmp")) / f"armory_backup_{uuid.uuid4().hex}"
        archive_dir.mkdir(parents=True, exist_ok=True)
    local_archive = archive_dir / archive_name

    _backup_jobs[job_id] = {
        "status": "starting",
        "archive_name": archive_name,
        "target": target,
        "total": 0,
        "processed": 0,
        "total_size": 0,
        "processed_size": 0,
        "current_file": "",
        "created_at": datetime.now().isoformat(),
    }
    asyncio.create_task(
        _run_create_archive_async(
            yandex,
            db_path,
            uploads_src,
            local_archive,
            archive_name,
            job_id,
            target,
            archive_dir if target == "yandex" else None,
        )
    )
    return {"job_id": job_id}


async def _run_create_archive_async(
    yandex: YandexDiskStorage | None,
    db_path: Path,
    uploads_src: Path,
    local_archive: Path,
    archive_name: str,
    job_id: str,
    target: str,
    temporary_dir: Path | None,
) -> None:
    """Фоновая задача создания архива в выбранных хранилищах с прогрессом."""
    try:
        local_archive.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(_create_tarball, db_path, uploads_src, local_archive, job_id)

        if job_id in _backup_jobs and target in {"yandex", "both"}:
            _backup_jobs[job_id]["current_file"] = archive_name
            _backup_jobs[job_id]["status"] = "uploading"
            _backup_jobs[job_id]["total"] = 1
            _backup_jobs[job_id]["processed"] = 0
            _backup_jobs[job_id]["processed_size"] = 0
            _backup_jobs[job_id]["total_size"] = local_archive.stat().st_size

        if target in {"yandex", "both"}:
            if not yandex:
                raise RuntimeError("Яндекс.Диск не настроен")

            remote_path = f"{REMOTE_BACKUPS}/{archive_name}"
            await asyncio.to_thread(yandex.ensure_folders, remote_path)

            def _upload_progress(done, total):
                if job_id in _backup_jobs:
                    _backup_jobs[job_id]["processed_size"] = done
                    _backup_jobs[job_id]["total_size"] = total
                    _backup_jobs[job_id]["current_file_size"] = total

            uploaded = await asyncio.to_thread(
                yandex.upload_file_with_progress,
                str(local_archive),
                remote_path,
                True,
                _upload_progress,
            )
            if not uploaded:
                raise RuntimeError("Не удалось загрузить архив на Яндекс.Диск")

        if job_id in _backup_jobs:
            _backup_jobs[job_id]["status"] = "completed"
            _backup_jobs[job_id]["archive"] = archive_name
            _backup_jobs[job_id]["local_saved"] = target in {"local", "both"}
            _backup_jobs[job_id]["yandex_saved"] = target in {"yandex", "both"}
            _backup_jobs[job_id]["current_file"] = ""
    except Exception as e:
        if job_id in _backup_jobs:
            _backup_jobs[job_id]["status"] = "error"
            _backup_jobs[job_id]["error"] = str(e)
            _backup_jobs[job_id]["current_file"] = ""
    finally:
        if temporary_dir:
            shutil.rmtree(temporary_dir, ignore_errors=True)


@router.get("/job/{job_id}")
async def backup_job_status(job_id: str):
    _cleanup_old_backup_jobs()
    job = _backup_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return job


@router.get("/download")
async def download_archive(name: str, source: str = "local"):
    """Отправляет выбранный архив пользователю для скачивания."""
    name = _validate_archive_name(name)
    source = _validate_backup_source(source)

    if source == "local":
        archive_path = _local_archive_path(name)
        if not archive_path.is_file():
            raise HTTPException(status_code=404, detail="Локальный архив не найден")
        return FileResponse(
            archive_path,
            filename=name,
            media_type="application/gzip",
        )

    yandex = _get_yandex()
    if not yandex:
        raise HTTPException(status_code=503, detail="Яндекс.Диск не настроен")

    temp_dir = Path(os.environ.get("TMPDIR", "/tmp")) / f"armory_download_{uuid.uuid4().hex}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    archive_path = temp_dir / name
    downloaded = await asyncio.to_thread(
        yandex.download_file,
        f"{REMOTE_BACKUPS}/{name}",
        str(archive_path),
    )
    if not downloaded:
        _cleanup_archive_download(temp_dir)
        raise HTTPException(status_code=404, detail="Архив на Яндекс.Диске не найден")

    return FileResponse(
        archive_path,
        filename=name,
        media_type="application/gzip",
        background=BackgroundTask(_cleanup_archive_download, temp_dir),
    )


@router.post("/restore")
async def restore_archive(payload: dict | None = None):
    payload = payload or {}
    name = _validate_archive_name(payload.get("name"))
    source = _validate_backup_source(payload.get("source", "yandex"))
    yandex = _get_yandex() if source == "yandex" else None
    if source == "yandex" and not yandex:
        raise HTTPException(status_code=503, detail="Яндекс.Диск не настроен")

    db_path = Path(settings.database_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")).resolve()
    uploads_dst = Path(settings.local_storage_path).resolve()

    # Автоматический локальный бэкап перед destructive операцией
    auto_backup = await asyncio.to_thread(_local_auto_backup, db_path, uploads_dst)

    temp_dir = None
    if source == "yandex":
        temp_dir = Path(os.environ.get("TMPDIR", "/tmp")) / f"armory_restore_{uuid.uuid4().hex}"
        temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        if source == "local":
            local_archive = _local_archive_path(name)
            if not local_archive.is_file():
                raise HTTPException(status_code=404, detail="Локальный архив не найден")
        else:
            local_archive = temp_dir / name
            downloaded = await asyncio.to_thread(
                yandex.download_file,
                f"{REMOTE_BACKUPS}/{name}",
                str(local_archive),
            )
            if not downloaded:
                raise HTTPException(status_code=502, detail="Не удалось скачать архив с Яндекс.Диска")

        # Очищаем uploads перед распаковкой
        if uploads_dst.exists():
            for child in uploads_dst.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                elif child.is_file():
                    child.unlink()

        # Распаковываем
        await asyncio.to_thread(_extract_tarball, local_archive, db_path, uploads_dst)

        # Восстанавливаем БД из распакованного файла
        dump = await asyncio.to_thread(_read_sqlite_dump, db_path)
        async with AsyncSessionLocal() as session:
            db_stats = await _restore_dump(dump, session)

        return {
            "success": True,
            "stats": {
                **db_stats,
                "auto_backup": str(auto_backup),
            },
        }
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


@router.post("/delete")
async def delete_archive(payload: dict | None = None):
    payload = payload or {}
    name = _validate_archive_name(payload.get("name"))
    source = _validate_backup_source(payload.get("source", "yandex"))

    if source == "local":
        archive_path = _local_archive_path(name)
        if not archive_path.is_file():
            raise HTTPException(status_code=404, detail="Локальный архив не найден")
        archive_path.unlink()
        return {"success": True}

    yandex = _get_yandex()
    if not yandex:
        raise HTTPException(status_code=503, detail="Яндекс.Диск не настроен")

    remote_path = f"{REMOTE_BACKUPS}/{name}"
    ok = await asyncio.to_thread(yandex.delete, remote_path)
    if not ok:
        raise HTTPException(status_code=502, detail="Не удалось удалить архив с Яндекс.Диска")
    return {"success": True}


# ── эндпоинты Alexandrite ────────────────────────────────────────────

@router.get("/alexandrite/stats")
async def alexandrite_stats():
    yandex = _get_yandex()
    yandex_status = {"connected": False, "info": "Токен не настроен"}
    if yandex:
        conn = await asyncio.to_thread(yandex.test_connection)
        yandex_status = {
            "connected": conn["ok"],
            "info": conn.get("info", ""),
            "used": conn.get("used", ""),
            "total": conn.get("total", ""),
        }

    local_path = Path(settings.alexandrite_vault_path).expanduser().resolve()
    stats = _gather_alexandrite_stats(local_path)
    sync = _sync_state_payload()
    return {
        "local": stats,
        "yandex": yandex_status,
        "sync": {
            "last_sync_at": sync["alexandrite_last_sync_at"],
            "last_sync": sync["alexandrite_last_sync"],
        },
    }


@router.post("/alexandrite/export")
async def alexandrite_export():
    yandex = _get_yandex()
    if not yandex:
        raise HTTPException(status_code=503, detail="Яндекс.Диск не настроен")

    local_path = Path(settings.alexandrite_vault_path).expanduser().resolve()

    await asyncio.to_thread(yandex.create_folder, REMOTE_ALEXANDRITE)
    upload_stats = await asyncio.to_thread(_upload_alexandrite, yandex, local_path, REMOTE_ALEXANDRITE)
    last_sync_at = await asyncio.to_thread(_record_sync, "alexandrite_last_sync_at")

    stats = _gather_alexandrite_stats(local_path)
    return {
        "success": True,
        "stats": {
            **stats,
            "files_uploaded": upload_stats["uploaded"],
            "files_failed": upload_stats["failed"],
            "last_sync_at": last_sync_at,
            "last_sync": _format_dt(last_sync_at),
        },
    }


async def _run_alexandrite_export_async(yandex: YandexDiskStorage, local_path: Path, job_id: str) -> None:
    """Фоновая задача экспорта Alexandrite с обновлением статуса."""
    try:
        await asyncio.to_thread(yandex.create_folder, REMOTE_ALEXANDRITE)
        await asyncio.to_thread(_upload_alexandrite, yandex, local_path, REMOTE_ALEXANDRITE, job_id)
        last_sync_at = await asyncio.to_thread(_record_sync, "alexandrite_last_sync_at")
        if job_id in _alexandrite_export_jobs:
            _alexandrite_export_jobs[job_id]["status"] = "completed"
            _alexandrite_export_jobs[job_id]["last_sync_at"] = last_sync_at
            _alexandrite_export_jobs[job_id]["last_sync"] = _format_dt(last_sync_at)
            _alexandrite_export_jobs[job_id]["current_file"] = ""
    except Exception as e:
        if job_id in _alexandrite_export_jobs:
            _alexandrite_export_jobs[job_id]["status"] = "error"
            _alexandrite_export_jobs[job_id]["error"] = str(e)
            _alexandrite_export_jobs[job_id]["current_file"] = ""


@router.post("/alexandrite/export-async")
async def alexandrite_export_async():
    yandex = _get_yandex()
    if not yandex:
        raise HTTPException(status_code=503, detail="Яндекс.Диск не настроен")

    _cleanup_old_backup_jobs()

    local_path = Path(settings.alexandrite_vault_path).expanduser().resolve()
    job_id = str(uuid.uuid4())
    _alexandrite_export_jobs[job_id] = {
        "status": "starting",
        "total": 0,
        "uploaded": 0,
        "failed": 0,
        "processed": 0,
        "current_file": "",
        "created_at": datetime.now().isoformat(),
    }
    asyncio.create_task(_run_alexandrite_export_async(yandex, local_path, job_id))
    return {"job_id": job_id}


@router.get("/alexandrite/export-status/{job_id}")
async def alexandrite_export_status(job_id: str):
    _cleanup_old_backup_jobs()
    job = _alexandrite_export_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return job


@router.post("/alexandrite/import")
async def alexandrite_import():
    yandex = _get_yandex()
    if not yandex:
        raise HTTPException(status_code=503, detail="Яндекс.Диск не настроен")

    local_path = Path(settings.alexandrite_vault_path).expanduser().resolve()

    auto_backup = await asyncio.to_thread(_local_auto_backup_alexandrite, local_path)

    # Очищаем локальную папку перед скачиванием
    if local_path.exists():
        for child in local_path.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            elif child.is_file():
                child.unlink()
    else:
        local_path.mkdir(parents=True, exist_ok=True)

    download_stats = await asyncio.to_thread(_download_alexandrite, yandex, REMOTE_ALEXANDRITE, local_path)
    stats = _gather_alexandrite_stats(local_path)
    last_sync_at = await asyncio.to_thread(_record_sync, "alexandrite_last_sync_at")

    return {
        "success": True,
        "stats": {
            **stats,
            "files_downloaded": download_stats["downloaded"],
            "files_skipped": download_stats["skipped"],
            "auto_backup": str(auto_backup),
            "last_sync_at": last_sync_at,
            "last_sync": _format_dt(last_sync_at),
        },
    }


@router.post("/alexandrite/archive")
async def create_alexandrite_archive(payload: dict | None = None):
    payload = payload or {}
    yandex = _get_yandex()
    target = payload.get("backup_target")
    if target is None:
        target = "both" if yandex else "local"
    if not isinstance(target, str) or target not in _BACKUP_TARGETS:
        raise HTTPException(status_code=400, detail="Некорректное место сохранения бэкапа")
    if target in {"yandex", "both"} and not yandex:
        raise HTTPException(status_code=503, detail="Яндекс.Диск не настроен")

    local_path = Path(settings.alexandrite_vault_path).expanduser().resolve()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"alexandrite_backup_{ts}.tar.gz"
    temporary_dir = None
    if target in {"local", "both"}:
        LOCAL_BACKUPS.mkdir(parents=True, exist_ok=True)
        local_archive = _local_alexandrite_archive_path(archive_name)
    else:
        temporary_dir = Path(os.environ.get("TMPDIR", "/tmp")) / f"armory_alexandrite_backup_{uuid.uuid4().hex}"
        temporary_dir.mkdir(parents=True, exist_ok=True)
        local_archive = temporary_dir / archive_name

    try:
        await asyncio.to_thread(_create_alexandrite_tarball, local_path, local_archive)
        if target in {"yandex", "both"}:
            remote_path = f"{REMOTE_ALEXANDRITE_BACKUPS}/{archive_name}"
            await asyncio.to_thread(yandex.ensure_folders, remote_path)
            uploaded = await asyncio.to_thread(yandex.upload_file, str(local_archive), remote_path)
            if not uploaded:
                raise HTTPException(
                    status_code=502,
                    detail="Не удалось загрузить архив Alexandrite на Яндекс.Диск",
                )
        return {
            "success": True,
            "archive": archive_name,
            "target": target,
            "local_saved": target in {"local", "both"},
            "yandex_saved": target in {"yandex", "both"},
        }
    finally:
        if temporary_dir:
            shutil.rmtree(temporary_dir, ignore_errors=True)


@router.get("/alexandrite/archives")
async def list_alexandrite_archives():
    yandex = _get_yandex()
    backups = await asyncio.to_thread(_list_local_alexandrite_backups)
    if yandex:
        backups.extend(await asyncio.to_thread(_list_alexandrite_backups, yandex))
    backups.sort(key=_archive_sort_key)
    return {"archives": backups}


@router.get("/alexandrite/download")
async def download_alexandrite_archive(name: str, source: str = "local"):
    """Отправляет выбранный архив Alexandrite пользователю для скачивания."""
    name = _validate_alexandrite_archive_name(name)
    source = _validate_backup_source(source)

    if source == "local":
        archive_path = _local_alexandrite_archive_path(name)
        if not archive_path.is_file():
            raise HTTPException(status_code=404, detail="Локальный архив Alexandrite не найден")
        return FileResponse(
            archive_path,
            filename=name,
            media_type="application/gzip",
        )

    yandex = _get_yandex()
    if not yandex:
        raise HTTPException(status_code=503, detail="Яндекс.Диск не настроен")

    temp_dir = Path(os.environ.get("TMPDIR", "/tmp")) / f"armory_alexandrite_download_{uuid.uuid4().hex}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    archive_path = temp_dir / name
    downloaded = await asyncio.to_thread(
        yandex.download_file,
        f"{REMOTE_ALEXANDRITE_BACKUPS}/{name}",
        str(archive_path),
    )
    if not downloaded:
        _cleanup_archive_download(temp_dir)
        raise HTTPException(status_code=404, detail="Архив Alexandrite на Яндекс.Диске не найден")

    return FileResponse(
        archive_path,
        filename=name,
        media_type="application/gzip",
        background=BackgroundTask(_cleanup_archive_download, temp_dir),
    )


@router.post("/alexandrite/restore")
async def restore_alexandrite_archive(payload: dict | None = None):
    payload = payload or {}
    name = _validate_alexandrite_archive_name(payload.get("name"))
    source = _validate_backup_source(payload.get("source", "yandex"))
    yandex = _get_yandex() if source == "yandex" else None
    if source == "yandex" and not yandex:
        raise HTTPException(status_code=503, detail="Яндекс.Диск не настроен")

    local_path = Path(settings.alexandrite_vault_path).expanduser().resolve()
    temp_dir = None
    if source == "local":
        local_archive = _local_alexandrite_archive_path(name)
        if not local_archive.is_file():
            raise HTTPException(status_code=404, detail="Локальный архив Alexandrite не найден")
    else:
        temp_dir = Path(os.environ.get("TMPDIR", "/tmp")) / f"armory_alexandrite_restore_{uuid.uuid4().hex}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        local_archive = temp_dir / name

    auto_backup = await asyncio.to_thread(_local_auto_backup_alexandrite, local_path)

    try:
        if source == "yandex":
            downloaded = await asyncio.to_thread(
                yandex.download_file,
                f"{REMOTE_ALEXANDRITE_BACKUPS}/{name}",
                str(local_archive),
            )
            if not downloaded:
                raise HTTPException(status_code=502, detail="Не удалось скачать архив Alexandrite с Яндекс.Диска")

        # Очищаем локальную папку перед распаковкой
        if local_path.exists():
            for child in local_path.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                elif child.is_file():
                    child.unlink()
        else:
            local_path.mkdir(parents=True, exist_ok=True)

        await asyncio.to_thread(_extract_alexandrite_tarball, local_archive, local_path)
        stats = _gather_alexandrite_stats(local_path)

        return {
            "success": True,
            "stats": {
                **stats,
                "auto_backup": str(auto_backup),
            },
        }
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


@router.post("/alexandrite/delete")
async def delete_alexandrite_archive(payload: dict | None = None):
    payload = payload or {}
    name = _validate_alexandrite_archive_name(payload.get("name"))
    source = _validate_backup_source(payload.get("source", "yandex"))

    if source == "local":
        archive_path = _local_alexandrite_archive_path(name)
        if not archive_path.is_file():
            raise HTTPException(status_code=404, detail="Локальный архив Alexandrite не найден")
        archive_path.unlink()
        return {"success": True}

    yandex = _get_yandex()
    if not yandex:
        raise HTTPException(status_code=503, detail="Яндекс.Диск не настроен")

    remote_path = f"{REMOTE_ALEXANDRITE_BACKUPS}/{name}"
    ok = await asyncio.to_thread(yandex.delete, remote_path)
    if not ok:
        raise HTTPException(status_code=502, detail="Не удалось удалить архив Alexandrite с Яндекс.Диска")
    return {"success": True}
