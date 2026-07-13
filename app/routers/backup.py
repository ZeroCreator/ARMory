import asyncio
import os
import shutil
import sqlite3
import tarfile
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

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
)
from app.yandex_disk import YandexDiskStorage

router = APIRouter(prefix="/api/backup", tags=["backup"])

settings = get_settings()

_YANDEX_BASE = settings.yandex_disk_path.strip("/")
REMOTE_DB = f"{_YANDEX_BASE}/projectdocs.db"
REMOTE_UPLOADS = f"{_YANDEX_BASE}/uploads"
REMOTE_BACKUPS = settings.yandex_disk_backups_path.strip("/")
REMOTE_ALEXANDRITE = settings.yandex_disk_alexandrite_path.strip("/")
REMOTE_ALEXANDRITE_BACKUPS = f"{REMOTE_BACKUPS}/alexandrite"

# Хранилище фоновых задач экспорта/архивирования (job_id -> status)
_backup_jobs: Dict[str, dict] = {}
_alexandrite_export_jobs: Dict[str, dict] = {}


def _cleanup_old_backup_jobs() -> None:
    """Удаляет задачи старше 24 часов, чтобы не текла память."""
    cutoff = datetime.now() - timedelta(hours=24)
    for store in (_backup_jobs, _alexandrite_export_jobs):
        expired = [
            job_id for job_id, job in store.items()
            if datetime.fromisoformat(job.get("created_at", "2000-01-01T00:00:00")) < cutoff
        ]
        for job_id in expired:
            del store[job_id]


def _get_yandex() -> YandexDiskStorage | None:
    token = settings.yandex_disk_token
    if not token:
        return None
    return YandexDiskStorage(token, _YANDEX_BASE)


async def _gather_stats(session: AsyncSession) -> dict:
    projects = await session.execute(select(Project))
    sections = await session.execute(select(Section))
    documents = await session.execute(select(Document))
    items = await session.execute(select(DocumentItem))
    blocks = await session.execute(select(SidebarBlock))
    links = await session.execute(select(SidebarLink))
    events = await session.execute(select(CalendarEvent))
    task_statuses = await session.execute(select(TaskStatus))
    tasks = await session.execute(select(Task))

    proj_list = projects.scalars().all()
    sec_list = sections.scalars().all()
    doc_list = documents.scalars().all()
    item_list = items.scalars().all()
    block_list = blocks.scalars().all()
    link_list = links.scalars().all()
    event_list = events.scalars().all()
    status_list = task_statuses.scalars().all()
    task_list = tasks.scalars().all()

    links_count = sum(1 for i in item_list if i.item_type.value == "link")
    files_count = sum(1 for i in item_list if i.item_type.value == "file")
    notes_count = sum(1 for i in item_list if i.item_type.value == "note")
    sidebar_link_notes = sum(1 for l in link_list if l.note and l.note.strip())

    total_size = 0
    uploads_path = Path(settings.local_storage_path).resolve()
    for i in item_list:
        if i.item_type.value == "file" and i.file_path:
            fp = uploads_path / i.file_path
            if fp.exists():
                total_size += fp.stat().st_size

    return {
        "projects": len(proj_list),
        "sections": len(sec_list),
        "documents": len(doc_list),
        "links": links_count,
        "files": files_count,
        "notes": notes_count,
        "sidebar_blocks": len(block_list),
        "sidebar_links": len(link_list),
        "sidebar_link_notes": sidebar_link_notes,
        "calendar_events": len(event_list),
        "task_statuses": len(status_list),
        "tasks": len(task_list),
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

def _local_auto_backup(db_path: Path, uploads_src: Path) -> Path:
    """Создаёт локальную резервную копию перед destructive операциями."""
    backup_dir = Path("data/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    auto_dir = backup_dir / f"auto_{ts}"
    auto_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_path, auto_dir / "projectdocs.db")
    if uploads_src.exists():
        shutil.copytree(uploads_src, auto_dir / "uploads", dirs_exist_ok=True)
    return auto_dir


def _create_tarball(db_path: Path, uploads_src: Path, dest_path: Path, job_id: str | None = None) -> None:
    """Создаёт tar.gz с БД и uploads, обновляя прогресс в задаче."""
    files_to_add = [(db_path, "projectdocs.db")]
    if uploads_src.exists():
        for fp in uploads_src.rglob("*"):
            if fp.is_file():
                arcname = "uploads/" + fp.relative_to(uploads_src).as_posix()
                files_to_add.append((fp, arcname))

    total_size = sum(fp.stat().st_size for fp, _ in files_to_add)
    processed_size = 0

    if job_id and job_id in _backup_jobs:
        _backup_jobs[job_id]["total"] = len(files_to_add)
        _backup_jobs[job_id]["total_size"] = total_size
        _backup_jobs[job_id]["status"] = "packing"

    with tarfile.open(dest_path, "w:gz") as tar:
        for idx, (fp, arcname) in enumerate(files_to_add, start=1):
            tar.add(fp, arcname=arcname)
            processed_size += fp.stat().st_size
            if job_id and job_id in _backup_jobs:
                _backup_jobs[job_id]["processed"] = idx
                _backup_jobs[job_id]["processed_size"] = processed_size
                _backup_jobs[job_id]["current_file"] = arcname

    if job_id and job_id in _backup_jobs:
        _backup_jobs[job_id]["status"] = "running"


def _extract_tarball(tar_path: Path, db_dest: Path, uploads_dest: Path) -> None:
    """Распаковывает tar.gz в указанные пути."""
    with tarfile.open(tar_path, "r:gz") as tar:
        for member in tar.getmembers():
            if member.name == "projectdocs.db":
                extracted = tar.extractfile(member)
                if extracted:
                    db_dest.write_bytes(extracted.read())
            elif member.name.startswith("uploads/"):
                extracted = tar.extractfile(member)
                if extracted:
                    rel = member.name[len("uploads/"):]
                    out_path = uploads_dest / rel
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_bytes(extracted.read())


def _list_backups(yandex: YandexDiskStorage) -> list:
    """Возвращает список tar.gz архивов на Я.Диске в папке бэкапов."""
    items = yandex.list_files(REMOTE_BACKUPS)
    backups = []
    for item in items:
        if item.get("type") == "file" and item.get("name", "").endswith(".tar.gz"):
            backups.append({
                "name": item["name"],
                "size": item.get("size", 0),
                "modified": _format_dt(item.get("modified", "")),
            })
    return sorted(backups, key=lambda x: x.get("modified", ""), reverse=True)


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
    with tarfile.open(dest_path, "w:gz") as tar:
        if local_src.exists():
            for fp in local_src.rglob("*"):
                if fp.is_file() and not _is_hidden_path(fp, local_src):
                    arcname = "alexandrite/" + fp.relative_to(local_src).as_posix()
                    tar.add(fp, arcname=arcname)


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
                    out_path.write_bytes(extracted.read())


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
        if item.get("type") == "file" and name.endswith(".tar.gz") and name.startswith("alexandrite_backup_"):
            backups.append({
                "name": name,
                "size": item.get("size", 0),
                "modified": _format_dt(item.get("modified", "")),
            })
    return sorted(backups, key=lambda x: x.get("modified", ""), reverse=True)


# ── эндпоинты ────────────────────────────────────────────────────────


@router.get("/stats")
async def backup_stats():
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

    return {"local": stats, "yandex": yandex_status}


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
            _backup_jobs[job_id]["current_file"] = "projectdocs.db"

        await asyncio.to_thread(yandex.create_folder, _YANDEX_BASE)
        await asyncio.to_thread(yandex.create_folder, REMOTE_UPLOADS)

        db_uploaded = await asyncio.to_thread(yandex.upload_file, str(db_path), REMOTE_DB)
        if not db_uploaded:
            raise RuntimeError("Не удалось загрузить projectdocs.db на Яндекс.Диск")

        upload_stats = await asyncio.to_thread(_upload_uploads, yandex, uploads_src, REMOTE_UPLOADS, job_id)

        async with AsyncSessionLocal() as session:
            stats = await _gather_stats(session)

        if job_id in _backup_jobs:
            _backup_jobs[job_id]["status"] = "completed"
            _backup_jobs[job_id]["stats"] = {
                **{k: v for k, v in stats.items()},
                "db_uploaded": db_uploaded,
                "files_uploaded": upload_stats["uploaded"],
                "files_skipped": upload_stats["skipped"],
                "auto_backup": str(auto_backup),
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
        local_db = temp_dir / "projectdocs.db"
        db_downloaded = await asyncio.to_thread(yandex.download_file, REMOTE_DB, str(local_db))
        if not db_downloaded:
            raise HTTPException(status_code=502, detail="Не удалось скачать projectdocs.db с Яндекс.Диска. Возможно, синхронизация ещё не выполнялась.")

        # Читаем sqlite dump
        dump = await asyncio.to_thread(_read_sqlite_dump, local_db)

        # Восстанавливаем БД
        async with AsyncSessionLocal() as session:
            db_stats = await _restore_dump(dump, session)

        # Скачиваем uploads
        uploads_dst = Path(settings.local_storage_path).resolve()
        uploads_dst.mkdir(parents=True, exist_ok=True)
        file_stats = await asyncio.to_thread(_download_uploads, yandex, REMOTE_UPLOADS, uploads_dst)

        return {
            "success": True,
            "stats": {
                **db_stats,
                "files_downloaded": file_stats["downloaded"],
                "files_skipped": file_stats["skipped"],
                "auto_backup": str(auto_backup),
            },
        }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ── эндпоинты архивов ────────────────────────────────────────────────

@router.get("/archives")
async def list_archives():
    yandex = _get_yandex()
    if not yandex:
        raise HTTPException(status_code=503, detail="Яндекс.Диск не настроен")
    backups = await asyncio.to_thread(_list_backups, yandex)
    return {"archives": backups}


@router.post("/create")
async def create_archive():
    yandex = _get_yandex()
    if not yandex:
        raise HTTPException(status_code=503, detail="Яндекс.Диск не настроен")

    _cleanup_old_backup_jobs()

    db_path = Path(settings.database_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")).resolve()
    uploads_src = Path(settings.local_storage_path).resolve()

    job_id = str(uuid.uuid4())
    archive_name = f"armory_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tar.gz"
    local_archive = Path(os.environ.get("TMPDIR", "/tmp")) / archive_name

    _backup_jobs[job_id] = {
        "status": "starting",
        "archive_name": archive_name,
        "total": 0,
        "processed": 0,
        "total_size": 0,
        "processed_size": 0,
        "current_file": "",
        "created_at": datetime.now().isoformat(),
    }
    asyncio.create_task(_run_create_archive_async(yandex, db_path, uploads_src, local_archive, archive_name, job_id))
    return {"job_id": job_id}


async def _run_create_archive_async(
    yandex: YandexDiskStorage,
    db_path: Path,
    uploads_src: Path,
    local_archive: Path,
    archive_name: str,
    job_id: str,
) -> None:
    """Фоновая задача создания архива и загрузки на Яндекс.Диск с прогрессом."""
    try:
        await asyncio.to_thread(_create_tarball, db_path, uploads_src, local_archive, job_id)

        if job_id in _backup_jobs:
            _backup_jobs[job_id]["current_file"] = archive_name
            _backup_jobs[job_id]["status"] = "uploading"

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
            _backup_jobs[job_id]["current_file"] = ""
    except Exception as e:
        if job_id in _backup_jobs:
            _backup_jobs[job_id]["status"] = "error"
            _backup_jobs[job_id]["error"] = str(e)
            _backup_jobs[job_id]["current_file"] = ""
    finally:
        if local_archive.exists():
            local_archive.unlink()


@router.get("/job/{job_id}")
async def backup_job_status(job_id: str):
    job = _backup_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return job


@router.post("/restore")
async def restore_archive(payload: dict):
    yandex = _get_yandex()
    if not yandex:
        raise HTTPException(status_code=503, detail="Яндекс.Диск не настроен")

    name = payload.get("name")
    if not name or not name.endswith(".tar.gz"):
        raise HTTPException(status_code=400, detail="Некорректное имя архива")

    db_path = Path(settings.database_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")).resolve()
    uploads_dst = Path(settings.local_storage_path).resolve()

    # Автоматический локальный бэкап перед destructive операцией
    auto_backup = await asyncio.to_thread(_local_auto_backup, db_path, uploads_dst)

    temp_dir = Path(os.environ.get("TMPDIR", "/tmp")) / f"armory_restore_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        remote_path = f"{REMOTE_BACKUPS}/{name}"
        local_archive = temp_dir / name
        downloaded = await asyncio.to_thread(yandex.download_file, remote_path, str(local_archive))
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
        shutil.rmtree(temp_dir, ignore_errors=True)


@router.post("/delete")
async def delete_archive(payload: dict):
    yandex = _get_yandex()
    if not yandex:
        raise HTTPException(status_code=503, detail="Яндекс.Диск не настроен")

    name = payload.get("name")
    if not name or not name.endswith(".tar.gz"):
        raise HTTPException(status_code=400, detail="Некорректное имя архива")

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
    return {"local": stats, "yandex": yandex_status}


@router.post("/alexandrite/export")
async def alexandrite_export():
    yandex = _get_yandex()
    if not yandex:
        raise HTTPException(status_code=503, detail="Яндекс.Диск не настроен")

    local_path = Path(settings.alexandrite_vault_path).expanduser().resolve()

    await asyncio.to_thread(yandex.create_folder, REMOTE_ALEXANDRITE)
    upload_stats = await asyncio.to_thread(_upload_alexandrite, yandex, local_path, REMOTE_ALEXANDRITE)

    stats = _gather_alexandrite_stats(local_path)
    return {
        "success": True,
        "stats": {
            **stats,
            "files_uploaded": upload_stats["uploaded"],
            "files_failed": upload_stats["failed"],
        },
    }


async def _run_alexandrite_export_async(yandex: YandexDiskStorage, local_path: Path, job_id: str) -> None:
    """Фоновая задача экспорта Alexandrite с обновлением статуса."""
    try:
        await asyncio.to_thread(yandex.create_folder, REMOTE_ALEXANDRITE)
        await asyncio.to_thread(_upload_alexandrite, yandex, local_path, REMOTE_ALEXANDRITE, job_id)
        if job_id in _alexandrite_export_jobs:
            _alexandrite_export_jobs[job_id]["status"] = "completed"
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

    return {
        "success": True,
        "stats": {
            **stats,
            "files_downloaded": download_stats["downloaded"],
            "files_skipped": download_stats["skipped"],
            "auto_backup": str(auto_backup),
        },
    }


@router.post("/alexandrite/archive")
async def create_alexandrite_archive():
    yandex = _get_yandex()
    if not yandex:
        raise HTTPException(status_code=503, detail="Яндекс.Диск не настроен")

    local_path = Path(settings.alexandrite_vault_path).expanduser().resolve()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"alexandrite_backup_{ts}.tar.gz"
    local_archive = Path(os.environ.get("TMPDIR", "/tmp")) / archive_name

    try:
        await asyncio.to_thread(_create_alexandrite_tarball, local_path, local_archive)
        remote_path = f"{REMOTE_ALEXANDRITE_BACKUPS}/{archive_name}"
        await asyncio.to_thread(yandex.ensure_folders, remote_path)
        uploaded = await asyncio.to_thread(yandex.upload_file, str(local_archive), remote_path)
        if not uploaded:
            raise HTTPException(status_code=502, detail="Не удалось загрузить архив Alexandrite на Яндекс.Диск")
        return {"success": True, "archive": archive_name}
    finally:
        if local_archive.exists():
            local_archive.unlink()


@router.get("/alexandrite/archives")
async def list_alexandrite_archives():
    yandex = _get_yandex()
    if not yandex:
        raise HTTPException(status_code=503, detail="Яндекс.Диск не настроен")
    backups = await asyncio.to_thread(_list_alexandrite_backups, yandex)
    return {"archives": backups}


@router.post("/alexandrite/restore")
async def restore_alexandrite_archive(payload: dict):
    yandex = _get_yandex()
    if not yandex:
        raise HTTPException(status_code=503, detail="Яндекс.Диск не настроен")

    name = payload.get("name")
    if not name or not name.endswith(".tar.gz"):
        raise HTTPException(status_code=400, detail="Некорректное имя архива")

    local_path = Path(settings.alexandrite_vault_path).expanduser().resolve()
    auto_backup = await asyncio.to_thread(_local_auto_backup_alexandrite, local_path)

    temp_dir = Path(os.environ.get("TMPDIR", "/tmp")) / f"armory_alexandrite_restore_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        remote_path = f"{REMOTE_ALEXANDRITE_BACKUPS}/{name}"
        local_archive = temp_dir / name
        downloaded = await asyncio.to_thread(yandex.download_file, remote_path, str(local_archive))
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
        shutil.rmtree(temp_dir, ignore_errors=True)


@router.post("/alexandrite/delete")
async def delete_alexandrite_archive(payload: dict):
    yandex = _get_yandex()
    if not yandex:
        raise HTTPException(status_code=503, detail="Яндекс.Диск не настроен")

    name = payload.get("name")
    if not name or not name.endswith(".tar.gz"):
        raise HTTPException(status_code=400, detail="Некорректное имя архива")

    remote_path = f"{REMOTE_ALEXANDRITE_BACKUPS}/{name}"
    ok = await asyncio.to_thread(yandex.delete, remote_path)
    if not ok:
        raise HTTPException(status_code=502, detail="Не удалось удалить архив Alexandrite с Яндекс.Диска")
    return {"success": True}
