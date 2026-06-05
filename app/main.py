"""
ProJectDocsHub — веб-приложение для сбора и управления документами проектов.

Author: Shkola Olga
"""
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
from sqlalchemy import text

from app.database import engine, Base
from app.routers import projects, documents, sidebar, scheduler, calendar, backup
from app.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Migration: split Document (old flat model) into Document (group) + DocumentItem
        tables = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        table_names = [r[0] for r in tables.fetchall()]

        if "document_items" not in table_names:
            # Create items table manually if SQLAlchemy hasn't yet
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

        # Check if old flat schema still exists (has doc_type column in documents)
        doc_cols = await conn.execute(text("PRAGMA table_info(documents)"))
        doc_column_names = [r[1] for r in doc_cols.fetchall()]

        if "doc_type" in doc_column_names:
            # Migrate old flat documents into group + items
            await conn.execute(text("""
                INSERT INTO document_items (document_id, item_type, url, file_path, file_name, file_size, mime_type, sort_order, created_at)
                SELECT id, doc_type, url, file_path, file_name, file_size, mime_type, sort_order, created_at FROM documents
            """))

            # Rebuild documents table without old flat columns
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

            # Fix sequence only if sqlite_sequence table exists (AUTOINCREMENT tables)
            seq_tables = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'"))
            if seq_tables.fetchone():
                await conn.execute(text("""
                    INSERT OR REPLACE INTO sqlite_sequence (name, seq)
                    SELECT 'documents', COALESCE(MAX(id), 0) FROM documents
                """))

        # Fix broken FK: if document_items still references documents_old, rebuild it
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

        # Add missing columns to document_items
        item_cols = await conn.execute(text("PRAGMA table_info(document_items)"))
        item_column_names = [r[1] for r in item_cols.fetchall()]
        if "category" not in item_column_names:
            await conn.execute(text("ALTER TABLE document_items ADD COLUMN category VARCHAR(50)"))
        if "title" not in item_column_names:
            await conn.execute(text("ALTER TABLE document_items ADD COLUMN title VARCHAR(255)"))
        if "content" not in item_column_names:
            await conn.execute(text("ALTER TABLE document_items ADD COLUMN content TEXT"))

        # Cleanup old backup table if still exists
        old_tables = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='documents_old'"))
        if old_tables.fetchone():
            await conn.execute(text("DROP TABLE documents_old"))

        # Migration: add sort_order to projects
        project_cols = await conn.execute(text("PRAGMA table_info(projects)"))
        project_col_names = [r[1] for r in project_cols.fetchall()]
        if "sort_order" not in project_col_names:
            await conn.execute(text("ALTER TABLE projects ADD COLUMN sort_order INTEGER DEFAULT 0"))

        # Migration: sidebar blocks & links
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

        # Migration: add sections support
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

        # Add description to sections if missing
        sec_cols = await conn.execute(text("PRAGMA table_info(sections)"))
        sec_col_names = [r[1] for r in sec_cols.fetchall()]
        if "description" not in sec_col_names:
            await conn.execute(text("ALTER TABLE sections ADD COLUMN description TEXT"))

        # Migration: calendar_events table
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

    # Seed default sidebar data from bd-arm if tables are empty
    from app.database import AsyncSessionLocal
    from app.models import SidebarBlock, SidebarLink
    from sqlalchemy import select, func

    async with AsyncSessionLocal() as seed_session:
        result = await seed_session.execute(select(func.count()).select_from(SidebarBlock))
        if result.scalar() == 0:
            left_blocks = [
                ("Мониторинг", [
                    ("Grafana", "https://grafana.team-73.ru/dashboards"),
                    ("SSK Flat Parser", "https://grafana.team-73.ru/d/9ff5ee31-7298-4d86-9ffc-d287b2e61190/ssk-flat-parser?orgId=1&from=now-5m&to=now&timezone=browser"),
                    ("Grafana-local", "http://localhost:3000/dashboards/"),
                ]),
                ("Коммуникации", [
                    ("Nextcloud-dashboard", "https://nc.team-73.ru/apps/dashboard/"),
                    ("Nextcloud Mail - Почта team-73.ru", "https://nc.team-73.ru/apps/mail/box/99"),
                    ("Телемост для совещаний", "https://telemost.yandex.ru/j/07852778496092"),
                ]),
                ("Репозитории GIT", [
                    ("GitHub CusDeb Solutions", "https://github.com/CusDeb-Solutions"),
                    ("GitHub team-73", "https://github.com/team-73"),
                    ("forgejo team-73", "https://forgejo.team-73.ru/explore/repos"),
                ]),
                ("Дополнительные инструменты", [
                    ("Adminer", "http://10.10.100.220:8080"),
                    ("WorkFlows", "http://10.10.100.220:5678"),
                    ("RabbitMQ", "http://10.10.103.22:15672"),
                    ("Quickwit", "http://lin-marketplace-logs:7280/ui/search"),
                    ("Quickwit-local", "http://localhost:7280/ui/search"),
                ]),
                ("Дока", [
                    ("WEB-docs", "https://web-docs.km-union.ru/books"),
                    ("KM-docs", "https://doc.km-union.ru/"),
                    ("Scripts-docs", "https://zerocreator.github.io/scripts/"),
                    ("Установка Grafana локально", "/readme/grafana-local-install"),
                    ("Nodriver-docs", "https://ultrafunkamsterdam.github.io/nodriver/"),
                ]),
            ]
            right_blocks = [
                ("Ресурсы разработки", [
                    ("Docs python", "https://docs.python.org/3/library/index.html"),
                    ("Nodriver", "https://github.com/ultrafunkamsterdam/nodriver"),
                    ("Яндекс.Метрика", "https://metrika.yandex.ru/"),
                    ("WorkFlow", "https://n8n.io/"),
                ]),
                ("Прокси", [
                    ("Proxy", "https://socproxy.ru/profile/proxy"),
                ]),
                ("AI chats", [
                    ("DeepSeek", "https://chat.deepseek.com/"),
                    ("Perplexity", "https://www.perplexity.ai/"),
                    ("Алиса AI", "https://alice.yandex.ru/"),
                ]),
                ("Homeo Remedy Book", [
                    ("GitHub Homeo Remedy Book", "https://github.com/ZeroCreator/homeoremedybook"),
                    ("Deploy Vercel Homeo Remedy Book", "https://vercel.com/zerocreators/homeoremedybook"),
                    ("Homeo Remedy Book", "https://homeoremedybook.vercel.app/"),
                ]),
                ("Homeo Remedy Test", [
                    ("GitHub Homeo Remedy Test", "https://github.com/ZeroCreator/homeoremedytest"),
                    ("Deploy Vercel Homeo Remedy Test", "https://vercel.com/zerocreators/homeoremedytest"),
                    ("Homeo Remedy Test", "https://homeoremedytest.vercel.app/"),
                ]),
                ("QUASARUM", [
                    ("GitHub QUASARUM", "https://github.com/ZeroCreator/quasarum"),
                    ("Deploy Vercel QUASARUM", "https://vercel.com/zerocreators/quasarum"),
                    ("QUASARUM", "https://quasarum.vercel.app/"),
                ]),
                ("Aid Kit", [
                    ("GitHub Aid Kit", "https://github.com/ZeroCreator/aid-kit"),
                    ("Deploy Vercel Aid Kit", "https://vercel.com/zerocreators/aid-kit"),
                    ("Aid Kit", "https://aid-kit.vercel.app/"),
                ]),
            ]

            for idx, (title, links) in enumerate(left_blocks):
                block = SidebarBlock(position="left", title=title, sort_order=idx)
                seed_session.add(block)
                await seed_session.flush()
                for lidx, (link_title, link_url) in enumerate(links):
                    seed_session.add(SidebarLink(block_id=block.id, title=link_title, url=link_url, sort_order=lidx))

            for idx, (title, links) in enumerate(right_blocks):
                block = SidebarBlock(position="right", title=title, sort_order=idx)
                seed_session.add(block)
                await seed_session.flush()
                for lidx, (link_title, link_url) in enumerate(links):
                    seed_session.add(SidebarLink(block_id=block.id, title=link_title, url=link_url, sort_order=lidx))

            await seed_session.commit()

    yield
    await engine.dispose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

# Static & templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# Routers
app.include_router(projects.router)
app.include_router(documents.router)
app.include_router(documents.section_router)
app.include_router(sidebar.router)
app.include_router(scheduler.router)
app.include_router(calendar.router)
app.include_router(backup.router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "title": settings.app_name})


@app.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_page(request: Request, project_id: int):
    return templates.TemplateResponse("project.html", {"request": request, "project_id": project_id, "title": settings.app_name})
