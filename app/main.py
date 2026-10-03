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
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from contextlib import asynccontextmanager
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from starlette.types import ASGIApp, Receive, Scope, Send
from urllib.parse import urlencode

from app.auth import get_email_from_scope
from app.database import engine, Base, AsyncSessionLocal
from app.routers import mcp_oauth
from app.routers import projects, documents, sidebar, scheduler, calendar, backup, alexandrite, wopi, collabora, tasks, assignees, extensions, mcp as mcp_router, events, comments, affairs, auth as auth_router
from app.config import get_settings
from app.extensions import enabled_extensions
from app.telegram import check_and_send_calendar_reminders

settings = get_settings()
logger = logging.getLogger(__name__)


def _is_auth_bypass_path(path: str) -> bool:
    """Маршруты с отдельной схемой авторизации, не зависящей от пользовательской сессии."""
    return path == "/mcp" or path.startswith("/mcp/") or path == "/wopi" or path.startswith("/wopi/")


def _is_auth_public_path(path: str) -> bool:
    return (
        path == "/auth"
        or path.startswith("/auth/")
        or path == "/static"
        or path.startswith("/static/")
        or path in {
            "/.well-known/oauth-protected-resource",
            "/.well-known/oauth-protected-resource/mcp",
            "/.well-known/oauth-authorization-server/mcp",
        }
    )


class RequireAuthMiddleware:
    """Не допускает анонимный доступ в публичном режиме ARMory."""

    def __init__(self, app: ASGIApp, settings):
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        path = scope.get("path", "")
        email = get_email_from_scope(scope, self.settings)
        if email:
            scope.setdefault("state", {})["user_email"] = email

        if (
            not self.settings.auth_required
            or scope["type"] not in {"http", "websocket"}
            or _is_auth_bypass_path(path)
            or _is_auth_public_path(path)
            or email
        ):
            await self.app(scope, receive, send)
            return

        if scope["type"] == "websocket":
            await send({
                "type": "websocket.close",
                "code": 1008,
                "reason": "Authentication required",
            })
            return

        if path == "/api" or path.startswith("/api/"):
            response = JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
                headers={"Cache-Control": "no-store"},
            )
        else:
            query_string = scope.get("query_string", b"").decode("latin-1")
            target = path + (f"?{query_string}" if query_string else "")
            location = "/auth/login?" + urlencode({"next": target})
            response = RedirectResponse(
                location,
                status_code=303,
                headers={"Cache-Control": "no-store"},
            )
        await response(scope, receive, send)


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


async def _ensure_affair_news_column(conn) -> None:
    columns = await conn.run_sync(
        lambda sync_conn: {column["name"] for column in inspect(sync_conn).get_columns("affairs")}
    )
    if "show_in_news" in columns:
        return

    backup_path = _backup_database_before_migration("affair_news")
    logger.info("Создан бэкап перед миграцией новостной ленты заметок: %s", backup_path)
    await conn.execute(text("ALTER TABLE affairs ADD COLUMN show_in_news BOOLEAN NOT NULL DEFAULT 0"))


async def _ensure_task_estimated_minutes_column(conn) -> None:
    columns = await conn.run_sync(
        lambda sync_conn: {column["name"] for column in inspect(sync_conn).get_columns("tasks")}
    )
    if "estimated_minutes" in columns:
        return

    backup_path = _backup_database_before_migration("task_estimated_minutes")
    logger.info("Создан бэкап перед добавлением плановой оценки задач: %s", backup_path)
    await conn.execute(text("ALTER TABLE tasks ADD COLUMN estimated_minutes INTEGER"))


async def _ensure_task_manual_time_columns(conn) -> None:
    columns = await conn.run_sync(
        lambda sync_conn: {column["name"] for column in inspect(sync_conn).get_columns("tasks")}
    )
    definitions = {
        "manual_work_seconds": "INTEGER",
        "manual_work_session_baseline": "INTEGER NOT NULL DEFAULT 0",
        "manual_testing_seconds": "INTEGER",
        "manual_testing_session_baseline": "INTEGER NOT NULL DEFAULT 0",
        "manual_actual_seconds": "INTEGER",
        "manual_actual_session_baseline": "INTEGER NOT NULL DEFAULT 0",
    }
    missing = {name: definition for name, definition in definitions.items() if name not in columns}
    if not missing:
        return

    backup_path = _backup_database_before_migration("task_manual_time")
    logger.info("Создан бэкап перед добавлением ручного учёта времени задач: %s", backup_path)
    for name, definition in missing.items():
        await conn.execute(text(f"ALTER TABLE tasks ADD COLUMN {name} {definition}"))


async def _ensure_task_time_completed_column(conn) -> None:
    """Добавляет признак завершения интервала после резервного копирования базы."""
    columns = await conn.run_sync(
        lambda sync_conn: {column["name"] for column in inspect(sync_conn).get_columns("task_time_sessions")}
    )
    if "completed" in columns:
        return
    backup_path = _backup_database_before_migration("task_time_completed")
    with sqlite3.connect(f"{backup_path.resolve().as_uri()}?mode=ro", uri=True) as backup_db:
        if backup_db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise RuntimeError("Проверка резервной копии перед добавлением статуса времени не пройдена")
    logger.info("Создан бэкап перед добавлением статуса времени: %s", backup_path)
    await conn.execute(text("ALTER TABLE task_time_sessions ADD COLUMN completed BOOLEAN NOT NULL DEFAULT 0"))


async def _close_stale_task_time_sessions(conn) -> None:
    await conn.execute(
        text("UPDATE task_time_sessions SET ended_at = :ended_at WHERE ended_at IS NULL"),
        {"ended_at": datetime.datetime.utcnow()},
    )


async def _ensure_mcp_oauth_schema(conn) -> None:
    """Сохраняет данные старого OAuth-хранилища при обновлении его формата."""
    columns = await conn.run_sync(
        lambda sync_conn: {
            table: {column["name"] for column in inspect(sync_conn).get_columns(table)}
            for table in ("mcp_oauth_clients", "mcp_oauth_tokens")
        }
    )
    client_columns = columns["mcp_oauth_clients"]
    rename_client_data = "client_info" not in client_columns and "client_data" in client_columns
    if "client_info" not in client_columns and not rename_client_data:
        raise RuntimeError("Неизвестная структура mcp_oauth_clients: нет client_info или client_data")

    if conn.dialect.name != "sqlite":
        if rename_client_data:
            raise RuntimeError("Обновление старого OAuth-хранилища требует резервной копии SQLite")
        return

    numeric_dates = []
    for column in ("expires_at", "revoked_at"):
        result = await conn.execute(text(
            f"SELECT 1 FROM mcp_oauth_tokens WHERE typeof({column}) IN ('integer', 'real') LIMIT 1"
        ))
        if result.first() is not None:
            invalid_dates = await conn.execute(text(
                f"SELECT 1 FROM mcp_oauth_tokens WHERE typeof({column}) IN ('integer', 'real') "
                f"AND strftime('%Y-%m-%d %H:%M:%f', {column}, 'unixepoch') IS NULL LIMIT 1"
            ))
            if invalid_dates.first() is not None:
                raise RuntimeError(f"Недопустимая числовая дата в mcp_oauth_tokens.{column}")
            numeric_dates.append(column)

    if not rename_client_data and not numeric_dates:
        return

    backup_path = _backup_database_before_migration("mcp_oauth")
    logger.info("Создан бэкап перед обновлением OAuth-хранилища MCP: %s", backup_path)
    if rename_client_data:
        await conn.execute(text(
            "ALTER TABLE mcp_oauth_clients RENAME COLUMN client_data TO client_info"
        ))
    for column in numeric_dates:
        await conn.execute(text(
            f"UPDATE mcp_oauth_tokens SET {column} = strftime('%Y-%m-%d %H:%M:%f', {column}, 'unixepoch') "
            f"WHERE typeof({column}) IN ('integer', 'real')"
        ))


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
        await _ensure_mcp_oauth_schema(conn)
        await _ensure_collapsed_columns(conn)
        await _ensure_affair_shared_column(conn)
        await _ensure_affair_news_column(conn)
        await _ensure_task_estimated_minutes_column(conn)
        await _ensure_task_manual_time_columns(conn)
        await _ensure_task_time_completed_column(conn)
        await _close_stale_task_time_sessions(conn)

        # Создаём data-директории, если их нет
        Path(settings.local_storage_path).expanduser().mkdir(parents=True, exist_ok=True)
        Path(settings.alexandrite_vault_path).expanduser().mkdir(parents=True, exist_ok=True)
        Path("data/backups").mkdir(parents=True, exist_ok=True)

    reminder_task = None
    if settings.telegram_reminder_enabled:
        reminder_task = asyncio.create_task(_reminder_loop())

    async with mcp_router.mcp_server.session_manager.run():
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
app.add_middleware(RequireAuthMiddleware, settings=settings)

# Статика и шаблоны
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/uploads", StaticFiles(directory=settings.local_storage_path), name="uploads")
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["enabled_extensions"] = enabled_extensions
templates.env.globals["personal_notes_enabled"] = settings.personal_notes_enabled
app.state.templates = templates
app.state.settings = settings

# Роутеры
app.include_router(auth_router.router)
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
app.include_router(mcp_oauth.router)
app.mount("/mcp", mcp_router.mcp_asgi_app, name="mcp")
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
    if not settings.personal_notes_enabled:
        raise HTTPException(status_code=404, detail="Раздел «Дела» отключён")

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


@app.get("/projects/{project_id}/tasks/time", response_class=HTMLResponse)
async def project_task_time_page(request: Request, project_id: int):
    return templates.TemplateResponse(
        "tasks_time.html",
        {
            "request": request,
            "project_id": project_id,
            "title": settings.app_name,
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


@app.get("/tasks/time", response_class=HTMLResponse)
async def global_task_time_page(request: Request):
    return templates.TemplateResponse(
        "tasks_time.html",
        {
            "request": request,
            "project_id": None,
            "title": settings.app_name,
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
    app.mount("/site", StaticFiles(directory=site_dir, html=True), name="landing-docs")

# Лендинг ARMory
landing_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "armory-landing"))
if os.path.isdir(landing_dir):
    app.mount("/landing", StaticFiles(directory=landing_dir, html=True), name="landing")
