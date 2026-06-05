import asyncio
import os
import shutil
import sqlite3
import tarfile
from datetime import datetime, timezone
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
)
from app.yandex_disk import YandexDiskStorage

router = APIRouter(prefix="/api/backup", tags=["backup"])

settings = get_settings()

_YANDEX_BASE = settings.yandex_disk_path.strip("/")
REMOTE_DB = f"{_YANDEX_BASE}/projectdocs.db"
REMOTE_UPLOADS = f"{_YANDEX_BASE}/uploads"
REMOTE_BACKUPS = settings.yandex_disk_backups_path.strip("/")


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

    proj_list = projects.scalars().all()
    sec_list = sections.scalars().all()
    doc_list = documents.scalars().all()
    item_list = items.scalars().all()
    block_list = blocks.scalars().all()
    link_list = links.scalars().all()
    event_list = events.scalars().all()

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
        "total_files_size": total_size,
    }


# ── helpers for Yandex Disk uploads/downloads ────────────────────────

def _upload_uploads(yandex: YandexDiskStorage, uploads_src: Path, remote_uploads: str) -> dict:
    """Синхронная загрузка всех файлов из uploads. Возвращает {uploaded, skipped}."""
    uploaded = 0
    skipped = 0
    if not uploads_src.exists():
        print("[BACKUP] uploads_src does not exist")
        return {"uploaded": 0, "skipped": 0}

    files = list(uploads_src.rglob("*"))
    file_list = [f for f in files if f.is_file()]
    print(f"[BACKUP] Found {len(file_list)} files to upload")

    for local_file in file_list:
        rel = local_file.relative_to(uploads_src)
        remote_path = f"{remote_uploads}/{rel.as_posix()}"
        print(f"[BACKUP] Uploading {rel} ...")
        ok = yandex.upload_file(str(local_file), remote_path)
        if ok:
            uploaded += 1
            print(f"[BACKUP] OK {rel}")
        else:
            print(f"[BACKUP] FAILED {rel}")

    print(f"[BACKUP] total uploaded={uploaded}, skipped={skipped}")
    return {"uploaded": uploaded, "skipped": skipped}


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


# ── restore helpers ──────────────────────────────────────────────────

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
    await session.execute(delete(Project))
    await session.commit()

    tables_order = [
        (Project, "projects"),
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
                    elif col.name in ("created_at", "updated_at", "start_date", "end_date") and isinstance(val, str):
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


# ── archive helpers ──────────────────────────────────────────────────

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


def _create_tarball(db_path: Path, uploads_src: Path, dest_path: Path) -> None:
    """Создаёт tar.gz с БД и uploads."""
    with tarfile.open(dest_path, "w:gz") as tar:
        tar.add(db_path, arcname="projectdocs.db")
        if uploads_src.exists():
            for fp in uploads_src.rglob("*"):
                if fp.is_file():
                    arcname = "uploads/" + fp.relative_to(uploads_src).as_posix()
                    tar.add(fp, arcname=arcname)


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


# ── endpoints ────────────────────────────────────────────────────────


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

    db_path = Path(settings.database_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")).resolve()
    uploads_src = Path(settings.local_storage_path).resolve()

    # Автоматический локальный бэкап перед destructive операцией
    auto_backup = await asyncio.to_thread(_local_auto_backup, db_path, uploads_src)

    # Создаём папки на Я.Диске
    await asyncio.to_thread(yandex.create_folder, _YANDEX_BASE)
    await asyncio.to_thread(yandex.create_folder, REMOTE_UPLOADS)

    # Загружаем БД
    db_uploaded = await asyncio.to_thread(yandex.upload_file, str(db_path), REMOTE_DB)
    if not db_uploaded:
        raise HTTPException(status_code=502, detail="Не удалось загрузить projectdocs.db на Яндекс.Диск")

    # Загружаем uploads
    upload_stats = await asyncio.to_thread(_upload_uploads, yandex, uploads_src, REMOTE_UPLOADS)

    async with AsyncSessionLocal() as session:
        stats = await _gather_stats(session)

    return {
        "success": True,
        "stats": {
            **stats,
            "db_uploaded": db_uploaded,
            "files_uploaded": upload_stats["uploaded"],
            "files_skipped": upload_stats["skipped"],
            "auto_backup": str(auto_backup),
        },
    }


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


# ── archive endpoints ────────────────────────────────────────────────

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

    db_path = Path(settings.database_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")).resolve()
    uploads_src = Path(settings.local_storage_path).resolve()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"armory_backup_{ts}.tar.gz"
    local_archive = Path(os.environ.get("TMPDIR", "/tmp")) / archive_name

    try:
        await asyncio.to_thread(_create_tarball, db_path, uploads_src, local_archive)
        remote_path = f"{REMOTE_BACKUPS}/{archive_name}"
        await asyncio.to_thread(yandex.ensure_folders, remote_path)
        uploaded = await asyncio.to_thread(yandex.upload_file, str(local_archive), remote_path)
        if not uploaded:
            raise HTTPException(status_code=502, detail="Не удалось загрузить архив на Яндекс.Диск")
        return {"success": True, "archive": archive_name}
    finally:
        if local_archive.exists():
            local_archive.unlink()


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
