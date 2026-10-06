from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.models import Project, Task, TaskStatus
from app.routers import tasks


@pytest_asyncio.fixture
async def attachment_api(tmp_path, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as db:
        db.add(Project(id=1, name="<project-name>"))
        db.add(TaskStatus(id=1, project_id=1, name="К выполнению", sort_order=0))
        db.add(Task(id=1, project_id=1, status_id=1, title="<task-title>"))
        await db.commit()

    monkeypatch.setattr(
        tasks,
        "get_settings",
        lambda: SimpleNamespace(local_storage_path=str(tmp_path), mcp_api_key="<mcp-api-key>"),
    )
    app = FastAPI()
    app.include_router(tasks.router)

    async def db_dependency():
        async with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = db_dependency

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://<service-host>",
    ) as client:
        yield client, tmp_path
    await engine.dispose()


@pytest.mark.asyncio
async def test_file_attachment_requires_uploaded_file(attachment_api):
    client, _ = attachment_api

    response = await client.post(
        "/api/projects/1/tasks/1/attachments",
        json={"attachment_type": "file", "url": "https://<your-domain>/document.md"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_uploaded_attachment_is_stored_as_file(attachment_api):
    client, storage_path = attachment_api

    response = await client.post(
        "/api/projects/1/tasks/1/attachments/upload",
        data={"title": "<document-title>"},
        files={"file": ("document.md", b"# document", "text/markdown")},
    )

    assert response.status_code == 201
    attachment = response.json()
    assert attachment["attachment_type"] == "file"
    assert attachment["url"] is None
    assert attachment["file_path"].startswith("tasks/")
    assert (storage_path / attachment["file_path"]).read_bytes() == b"# document"

    task = (await client.get("/api/projects/1/tasks/1")).json()
    assert task["attachments"] == [attachment]
