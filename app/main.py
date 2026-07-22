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

from app.database import engine, Base, AsyncSessionLocal
from app.routers import projects, documents, sidebar, scheduler, calendar, backup, alexandrite, glossary, wopi, collabora, tasks, assignees, pocketbase_proxy, mcp as mcp_router
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
app.include_router(mcp_router.router)
app.include_router(pocketbase_proxy.router, prefix="/pocketbase")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "title": settings.app_name,
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
