"""
ProJectDocsHub — веб-приложение для сбора и управления документами проектов.

Author: Shkola Olga
"""
import asyncio
import datetime
import logging
import os
import sqlite3
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

from app.database import engine, Base, AsyncSessionLocal
from app.routers import projects, documents, sidebar, scheduler, calendar, backup, alexandrite, wopi, collabora, tasks, assignees, extensions, mcp as mcp_router, events, comments, affairs
from app.config import get_settings
from app.extensions import enabled_extensions
from app.telegram import check_and_send_calendar_reminders

settings = get_settings()
logger = logging.getLogger(__name__)


def _backup_database_before_migration(label: str) -> Path:
    database_url = make_url(settings.database_url)
    if not database_url.drivername.startswith("sqlite") or not database_url.database:
        raise RuntimeError("Automatic collapsed-state migration requires a SQLite database backup")

    source = Path(database_url.database).resolve()
    backup_dir = Path("data/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = backup_dir / f"armory_pre_{label}_{timestamp}.db"
    with sqlite3.connect(source) as source_db, sqlite3.connect(destination) as backup_db:
        source_db.backup(backup_db)
    return destination


async def _ensure_collapsed_columns(conn) -> None:
    columns = await conn.run_sync(
        lambda sync_conn: {
            table: {column["name"] for column in inspect(sync_conn).get_columns(table)}
            for table in ("sections", "documents")
        }
    )
    missing_tables = [table for table, names in columns.items() if "collapsed" not in names]
    if not missing_tables:
        return

    backup_path = _backup_database_before_migration("collapsed")
    logger.info("Создан бэкап перед миграцией collapsed: %s", backup_path)
    for table in missing_tables:
        await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN collapsed BOOLEAN NOT NULL DEFAULT 1"))


async def _ensure_affair_shared_column(conn) -> None:
    columns = await conn.run_sync(
        lambda sync_conn: {column["name"] for column in inspect(sync_conn).get_columns("affairs")}
    )
    if "is_shared" in columns:
        return

    backup_path = _backup_database_before_migration("shared_notes")
    logger.info("Создан бэкап перед миграцией общих заметок: %s", backup_path)
    await conn.execute(text("ALTER TABLE affairs ADD COLUMN is_shared BOOLEAN NOT NULL DEFAULT 0"))


async def _reminder_loop():
    while True:
        try:
            async with AsyncSessionLocal() as session:
                await check_and_send_calendar_reminders(session)
        except Exception:
            logger.exception("Ошибка в цикле напоминаний календаря")
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_collapsed_columns(conn)
        await _ensure_affair_shared_column(conn)

        # Создаём data-директории, если их нет
        Path(settings.local_storage_path).expanduser().mkdir(parents=True, exist_ok=True)
        Path(settings.alexandrite_vault_path).expanduser().mkdir(parents=True, exist_ok=True)
        Path("data/backups").mkdir(parents=True, exist_ok=True)

    reminder_task = None
    if settings.telegram_reminder_enabled:
        reminder_task = asyncio.create_task(_reminder_loop())

    yield

    if reminder_task:
        reminder_task.cancel()
        try:
            await reminder_task
        except asyncio.CancelledError:
            pass

    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# Статика и шаблоны
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/uploads", StaticFiles(directory=settings.local_storage_path), name="uploads")
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["enabled_extensions"] = enabled_extensions
app.state.templates = templates

# Роутеры
app.include_router(projects.router)
app.include_router(documents.router)
app.include_router(documents.section_router)
app.include_router(sidebar.router)
app.include_router(scheduler.router)
app.include_router(calendar.router)
app.include_router(backup.router)
app.include_router(alexandrite.router)
app.include_router(wopi.router)
app.include_router(collabora.router)
app.include_router(tasks.router)
app.include_router(tasks.global_router)
app.include_router(assignees.router)
app.include_router(mcp_router.router)
app.include_router(events.router)
app.include_router(comments.router)
app.include_router(affairs.router)
app.include_router(extensions.router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "title": settings.app_name},
    )


@app.get("/synchronization", response_class=HTMLResponse)
async def synchronization_page(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "title": settings.app_name, "sync_page": True},
    )


@app.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_page(request: Request, project_id: int):
    return templates.TemplateResponse(
        "project.html",
        {
            "request": request,
            "project_id": project_id,
            "title": settings.app_name,
            "local_storage_path": settings.local_storage_path,
        },
    )


@app.get("/projects/{project_id}/kanban", response_class=HTMLResponse)
async def kanban_page(request: Request, project_id: int):
    return templates.TemplateResponse(
        "kanban.html",
        {
            "request": request,
            "project_id": project_id,
            "title": settings.app_name,
            "local_storage_path": settings.local_storage_path,
        },
    )


@app.get("/kanban", response_class=HTMLResponse)
async def global_kanban_page(request: Request):
    return templates.TemplateResponse(
        "kanban_global.html",
        {
            "request": request,
            "title": settings.app_name,
            "local_storage_path": settings.local_storage_path,
        },
    )


@app.get("/affairs", response_class=HTMLResponse)
async def affairs_page(request: Request):
    return templates.TemplateResponse(
        "affairs.html",
        {
            "request": request,
            "title": settings.app_name,
            "personal_notes_enabled": settings.personal_notes_enabled,
        },
    )


@app.get("/projects/{project_id}/tasks", response_class=HTMLResponse)
async def project_tasks_list_page(request: Request, project_id: int):
    return templates.TemplateResponse(
        "tasks_list.html",
        {
            "request": request,
            "project_id": project_id,
            "title": settings.app_name,
            "local_storage_path": settings.local_storage_path,
        },
    )


@app.get("/tasks", response_class=HTMLResponse)
async def global_tasks_list_page(request: Request):
    return templates.TemplateResponse(
        "tasks_list.html",
        {
            "request": request,
            "project_id": None,
            "title": settings.app_name,
            "local_storage_path": settings.local_storage_path,
        },
    )


@app.get("/alexandrite", response_class=HTMLResponse)
async def alexandrite_page(request: Request):
    return templates.TemplateResponse(
        "alexandrite.html",
        {"request": request, "title": settings.app_name},
    )


# Документация ARMory (MkDocs site)
site_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "site"))
if os.path.isdir(site_dir):
    app.mount("/docs", StaticFiles(directory=site_dir, html=True), name="docs")
