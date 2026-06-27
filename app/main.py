"""
ProJectDocsHub — веб-приложение для сбора и управления документами проектов.

Author: Shkola Olga
"""
import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
from sqlalchemy import text

from app.database import engine, Base
from app.routers import projects, documents, sidebar, scheduler, calendar, backup, alexandrite, glossary
from app.config import get_settings

settings = get_settings()


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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

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

    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# Статика и шаблоны
app.mount("/static", StaticFiles(directory="app/static"), name="static")
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


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "title": settings.app_name,
            "scheduler_enabled": settings.scheduler_enabled,
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
        },
    )


@app.get("/alexandrite", response_class=HTMLResponse)
async def alexandrite_page(request: Request):
    return templates.TemplateResponse("alexandrite.html", {"request": request, "title": settings.app_name})


@app.get("/glossary", response_class=HTMLResponse)
async def glossary_page(request: Request):
    return templates.TemplateResponse("glossary.html", {"request": request, "title": settings.app_name})


# Документация ARMory (MkDocs site)
site_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "site"))
if os.path.isdir(site_dir):
    app.mount("/docs", StaticFiles(directory=site_dir, html=True), name="docs")
