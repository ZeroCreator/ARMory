"""
ProJectDocsHub — веб-приложение для сбора и управления документами проектов.

Author: Shkola Olga
"""
import asyncio
import logging
import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
from sqlalchemy import text

from app.database import engine, Base, AsyncSessionLocal
from app.routers import projects, documents, sidebar, scheduler, calendar, backup, alexandrite, glossary, wopi, collabora, tasks, assignees, pocketbase_proxy
from app.config import get_settings
from app.telegram import check_and_send_calendar_reminders

settings = get_settings()
logger = logging.getLogger(__name__)


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

        # Миграция: разделить Document (старая плоская модель) на Document (группа) + DocumentItem
        tables = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        table_names = [r[0] for r in tables.fetchall()]

        if "document_items" not in table_names:
            # Создать таблицу элементов вручную, если SQLAlchemy ещё не создал
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS document_items (
                    id INTEGER PRIMARY KEY,
                    document_id INTEGER NOT NULL,
                    item_type VARCHAR(10) NOT NULL,
                    url TEXT,
                    file_path VARCHAR(500),
                    file_name VARCHAR(255),
                    file_size INTEGER,
                    mime_type VARCHAR(100),
                    sort_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
                )
            """))

        # Проверить, существует ли старая плоская схема (есть колонка doc_type в documents)
        doc_cols = await conn.execute(text("PRAGMA table_info(documents)"))
        doc_column_names = [r[1] for r in doc_cols.fetchall()]

        if "doc_type" in doc_column_names:
            # Мигрировать старые плоские документы в группу + элементы
            await conn.execute(text("""
                INSERT INTO document_items (document_id, item_type, url, file_path, file_name, file_size, mime_type, sort_order, created_at)
                SELECT id, doc_type, url, file_path, file_name, file_size, mime_type, sort_order, created_at FROM documents
            """))

            # Пересобрать таблицу documents без старых плоских колонок
            await conn.execute(text("ALTER TABLE documents RENAME TO documents_old"))
            await conn.execute(text("""
                CREATE TABLE documents (
                    id INTEGER PRIMARY KEY,
                    project_id INTEGER NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    category VARCHAR(50),
                    sort_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
            """))
            await conn.execute(text("""
                INSERT INTO documents (id, project_id, title, category, sort_order, created_at, updated_at)
                SELECT id, project_id, title, category, sort_order, created_at, updated_at FROM documents_old
            """))
            await conn.execute(text("DROP TABLE documents_old"))

            # Исправить sequence только если таблица sqlite_sequence существует (AUTOINCREMENT таблицы)
            seq_tables = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'"))
            if seq_tables.fetchone():
                await conn.execute(text("""
                    INSERT OR REPLACE INTO sqlite_sequence (name, seq)
                    SELECT 'documents', COALESCE(MAX(id), 0) FROM documents
                """))

        # Исправить сломанный FK: если document_items всё ещё ссылается на documents_old, пересобрать
        fk_info = await conn.execute(text("PRAGMA foreign_key_list(document_items)"))
        for row in fk_info.fetchall():
            if row[2] == "documents_old":
                await conn.execute(text("""
                    CREATE TABLE document_items_new (
                        id INTEGER PRIMARY KEY,
                        document_id INTEGER NOT NULL,
                        item_type VARCHAR(10) NOT NULL,
                        url TEXT,
                        file_path VARCHAR(500),
                        file_name VARCHAR(255),
                        file_size INTEGER,
                        mime_type VARCHAR(100),
                        sort_order INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
                    )
                """))
                await conn.execute(text("""
                    INSERT INTO document_items_new (id, document_id, item_type, url, file_path, file_name, file_size, mime_type, sort_order, created_at)
                    SELECT id, document_id, item_type, url, file_path, file_name, file_size, mime_type, sort_order, created_at FROM document_items
                """))
                await conn.execute(text("DROP TABLE document_items"))
                await conn.execute(text("ALTER TABLE document_items_new RENAME TO document_items"))
                break

        # Добавить недостающие колонки в document_items
        item_cols = await conn.execute(text("PRAGMA table_info(document_items)"))
        item_column_names = [r[1] for r in item_cols.fetchall()]
        if "category" not in item_column_names:
            await conn.execute(text("ALTER TABLE document_items ADD COLUMN category VARCHAR(50)"))
        if "title" not in item_column_names:
            await conn.execute(text("ALTER TABLE document_items ADD COLUMN title VARCHAR(255)"))
        if "content" not in item_column_names:
            await conn.execute(text("ALTER TABLE document_items ADD COLUMN content TEXT"))

        # Удалить старую таблицу бэкапа, если ещё существует
        old_tables = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='documents_old'"))
        if old_tables.fetchone():
            await conn.execute(text("DROP TABLE documents_old"))

        # Миграция: добавить sort_order в projects
        project_cols = await conn.execute(text("PRAGMA table_info(projects)"))
        project_col_names = [r[1] for r in project_cols.fetchall()]
        if "sort_order" not in project_col_names:
            await conn.execute(text("ALTER TABLE projects ADD COLUMN sort_order INTEGER DEFAULT 0"))

        # Миграция: боковые блоки и ссылки
        if "sidebar_blocks" not in table_names:
            await conn.execute(text("""
                CREATE TABLE sidebar_blocks (
                    id INTEGER PRIMARY KEY,
                    position VARCHAR(10) NOT NULL DEFAULT 'left',
                    title VARCHAR(255) NOT NULL,
                    sort_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
        if "sidebar_links" not in table_names:
            await conn.execute(text("""
                CREATE TABLE sidebar_links (
                    id INTEGER PRIMARY KEY,
                    block_id INTEGER NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    url TEXT NOT NULL,
                    sort_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (block_id) REFERENCES sidebar_blocks(id) ON DELETE CASCADE
                )
            """))

        # Миграция: добавить поддержку разделов
        if "sections" not in table_names:
            await conn.execute(text("""
                CREATE TABLE sections (
                    id INTEGER PRIMARY KEY,
                    project_id INTEGER NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    sort_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
            """))
        doc_cols2 = await conn.execute(text("PRAGMA table_info(documents)"))
        doc_col_names2 = [r[1] for r in doc_cols2.fetchall()]
        if "section_id" not in doc_col_names2:
            await conn.execute(text("ALTER TABLE documents ADD COLUMN section_id INTEGER"))
        if "description" not in doc_col_names2:
            await conn.execute(text("ALTER TABLE documents ADD COLUMN description TEXT"))

        # Добавить description в sections, если отсутствует
        sec_cols = await conn.execute(text("PRAGMA table_info(sections)"))
        sec_col_names = [r[1] for r in sec_cols.fetchall()]
        if "description" not in sec_col_names:
            await conn.execute(text("ALTER TABLE sections ADD COLUMN description TEXT"))

        # Миграция: таблица calendar_events
        if "calendar_events" not in table_names:
            await conn.execute(text("""
                CREATE TABLE calendar_events (
                    id INTEGER PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    description TEXT,
                    note TEXT,
                    start_date TIMESTAMP NOT NULL,
                    end_date TIMESTAMP,
                    all_day BOOLEAN DEFAULT 0,
                    color VARCHAR(7) DEFAULT '#a78bfa',
                    reminder_minutes INTEGER,
                    notified_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

        # Миграция: добавить поля напоминаний в существующую таблицу calendar_events
        if "calendar_events" in table_names:
            calendar_cols = await conn.execute(text("PRAGMA table_info(calendar_events)"))
            calendar_col_names = [r[1] for r in calendar_cols.fetchall()]
            if "reminder_minutes" not in calendar_col_names:
                await conn.execute(text("ALTER TABLE calendar_events ADD COLUMN reminder_minutes INTEGER"))
            if "notified_at" not in calendar_col_names:
                await conn.execute(text("ALTER TABLE calendar_events ADD COLUMN notified_at TIMESTAMP"))

        # Миграция: таблица glossary_terms
        if "glossary_terms" not in table_names:
            await conn.execute(text("""
                CREATE TABLE glossary_terms (
                    id INTEGER PRIMARY KEY,
                    term VARCHAR(255) NOT NULL,
                    short_definition TEXT,
                    definition TEXT,
                    letter VARCHAR(10),
                    sort_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

        # Миграция: ответственные (assignees)
        if "assignees" not in table_names:
            await conn.execute(text("""
                CREATE TABLE assignees (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

        # Миграция: заполнить assignees из существующих assignee_email задач
        if "tasks" in table_names and "assignees" in table_names:
            emails_result = await conn.execute(
                text("SELECT DISTINCT assignee_email FROM tasks WHERE assignee_email IS NOT NULL")
            )
            for (email,) in emails_result.fetchall():
                if not email:
                    continue
                existing = await conn.execute(
                    text("SELECT 1 FROM assignees WHERE email = :email"),
                    {"email": email},
                )
                if existing.fetchone():
                    continue
                name = email.split("@")[0]
                await conn.execute(
                    text("""
                        INSERT INTO assignees (name, email, created_at)
                        VALUES (:name, :email, CURRENT_TIMESTAMP)
                    """),
                    {"name": name, "email": email},
                )

        # Миграция: канбан (колонки и задачи)
        if "task_statuses" not in table_names:
            await conn.execute(text("""
                CREATE TABLE task_statuses (
                    id INTEGER PRIMARY KEY,
                    project_id INTEGER NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    color VARCHAR(7) NOT NULL DEFAULT '#a78bfa',
                    sort_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
            """))
        if "tasks" not in table_names:
            await conn.execute(text("""
                CREATE TABLE tasks (
                    id INTEGER PRIMARY KEY,
                    project_id INTEGER NOT NULL,
                    status_id INTEGER NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    description TEXT,
                    priority VARCHAR(20) DEFAULT 'medium',
                    due_date TIMESTAMP,
                    assignee_email VARCHAR(255),
                    tags VARCHAR(500),
                    list_name VARCHAR(255),
                    sort_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    FOREIGN KEY (status_id) REFERENCES task_statuses(id) ON DELETE CASCADE
                )
            """))
        else:
            columns_result = await conn.execute(text("PRAGMA table_info(tasks)"))
            task_columns = {row[1] for row in columns_result.fetchall()}
            if "list_name" not in task_columns:
                await conn.execute(text("ALTER TABLE tasks ADD COLUMN list_name VARCHAR(255)"))
        if "task_attachments" not in table_names:
            await conn.execute(text("""
                CREATE TABLE task_attachments (
                    id INTEGER PRIMARY KEY,
                    task_id INTEGER NOT NULL,
                    attachment_type VARCHAR(20) NOT NULL,
                    title VARCHAR(255),
                    url VARCHAR(1000),
                    file_path VARCHAR(500),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                )
            """))

        # Исправить NULL created_at в task_statuses (могли появиться из-за SQLAlchemy default без server_default)
        if "task_statuses" in table_names:
            await conn.execute(
                text("UPDATE task_statuses SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")
            )

        # Для существующих проектов без колонок создать дефолтные статусы канбана
        if "task_statuses" in table_names and "projects" in table_names:
            project_rows = await conn.execute(text("SELECT id FROM projects"))
            for (proj_id,) in project_rows.fetchall():
                existing = await conn.execute(
                    text("SELECT 1 FROM task_statuses WHERE project_id = :pid LIMIT 1"),
                    {"pid": proj_id},
                )
                if not existing.fetchone():
                    await conn.execute(
                        text("""
                            INSERT INTO task_statuses (project_id, name, color, sort_order, created_at)
                            VALUES
                                (:pid, 'К выполнению', '#a78bfa', 0, CURRENT_TIMESTAMP),
                                (:pid, 'В работе', '#f6ad55', 1, CURRENT_TIMESTAMP),
                                (:pid, 'Тестирование', '#63b3ed', 2, CURRENT_TIMESTAMP),
                                (:pid, 'Деплой', '#68d391', 3, CURRENT_TIMESTAMP)
                        """),
                        {"pid": proj_id},
                    )

        # Добавить колонку "Тестирование" перед "Деплой" в проектах, где её ещё нет
        if "task_statuses" in table_names and "projects" in table_names:
            project_rows = await conn.execute(text("SELECT id FROM projects"))
            for (proj_id,) in project_rows.fetchall():
                has_testing = await conn.execute(
                    text("SELECT 1 FROM task_statuses WHERE project_id = :pid AND name = 'Тестирование' LIMIT 1"),
                    {"pid": proj_id},
                )
                if has_testing.fetchone():
                    continue
                done_row = await conn.execute(
                    text("SELECT id, sort_order FROM task_statuses WHERE project_id = :pid AND name = 'Деплой' LIMIT 1"),
                    {"pid": proj_id},
                )
                done = done_row.fetchone()
                if done:
                    done_order = done[1]
                    await conn.execute(
                        text("UPDATE task_statuses SET sort_order = sort_order + 1 WHERE project_id = :pid AND sort_order >= :done_order"),
                        {"pid": proj_id, "done_order": done_order},
                    )
                    await conn.execute(
                        text("""
                            INSERT INTO task_statuses (project_id, name, color, sort_order, created_at)
                            VALUES (:pid, 'Тестирование', '#63b3ed', :done_order, CURRENT_TIMESTAMP)
                        """),
                        {"pid": proj_id, "done_order": done_order},
                    )

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

# Роутеры
app.include_router(projects.router)
app.include_router(documents.router)
app.include_router(documents.section_router)
app.include_router(sidebar.router)
app.include_router(scheduler.router)
app.include_router(calendar.router)
app.include_router(backup.router)
app.include_router(alexandrite.router)
app.include_router(glossary.router)
app.include_router(wopi.router)
app.include_router(collabora.router)
app.include_router(tasks.router)
app.include_router(tasks.global_router)
app.include_router(assignees.router)
app.include_router(pocketbase_proxy.router, prefix="/pocketbase")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "title": settings.app_name,
            "scheduler_enabled": settings.scheduler_enabled,
            "pocketbase_url": settings.pocketbase_public_url,
        },
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
            "pocketbase_url": settings.pocketbase_public_url,
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
            "pocketbase_url": settings.pocketbase_public_url,
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
            "pocketbase_url": settings.pocketbase_public_url,
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
            "pocketbase_url": settings.pocketbase_public_url,
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
            "pocketbase_url": settings.pocketbase_public_url,
        },
    )


@app.get("/alexandrite", response_class=HTMLResponse)
async def alexandrite_page(request: Request):
    return templates.TemplateResponse(
        "alexandrite.html",
        {"request": request, "title": settings.app_name, "pocketbase_url": settings.pocketbase_public_url},
    )


@app.get("/glossary", response_class=HTMLResponse)
async def glossary_page(request: Request):
    return templates.TemplateResponse(
        "glossary.html",
        {"request": request, "title": settings.app_name, "pocketbase_url": settings.pocketbase_public_url},
    )


# Документация ARMory (MkDocs site)
site_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "site"))
if os.path.isdir(site_dir):
    app.mount("/docs", StaticFiles(directory=site_dir, html=True), name="docs")
