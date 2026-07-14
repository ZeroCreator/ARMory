from datetime import datetime
from typing import Optional

import os
import platform
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import select, update, delete, func, distinct
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings, get_settings
from app.database import get_db
from app.models import Assignee, Project, Task, TaskAttachment, TaskStatus
from app.routers.collabora import build_collabora_iframe_url
from app.routers.wopi import OFFICE_EXTENSIONS, encode_file_id
from app.storage import StorageBackend, get_storage
from app.schemas import (
    GlobalKanbanColumnCreate,
    GlobalKanbanColumnUpdate,
    KanbanBoardOut,
    KanbanColumnOut,
    KanbanExportOut,
    KanbanFiltersOut,
    KanbanGlobalOut,
    KanbanImportIn,
    KanbanProjectExport,
    KanbanTaskStatusUpdate,
    TaskAttachmentCreate,
    TaskAttachmentOut,
    TaskCreate,
    TaskOut,
    TaskReorderRequest,
    TaskStatusCreate,
    TaskStatusOut,
    TaskStatusReorderRequest,
    TaskStatusUpdate,
    TaskUpdate,
)

router = APIRouter(prefix="/api/projects/{project_id}", tags=["tasks"])
global_router = APIRouter(prefix="/api", tags=["kanban"])


async def _get_project(project_id: int, db: AsyncSession) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _get_status(project_id: int, status_id: int, db: AsyncSession) -> TaskStatus:
    result = await db.execute(
        select(TaskStatus).where(TaskStatus.id == status_id, TaskStatus.project_id == project_id)
    )
    status = result.scalar_one_or_none()
    if not status:
        raise HTTPException(status_code=404, detail="Task status not found")
    return status


async def _get_task(project_id: int, task_id: int, db: AsyncSession) -> Task:
    result = await db.execute(
        select(Task)
        .options(selectinload(Task.status), selectinload(Task.attachments))
        .where(Task.id == task_id, Task.project_id == project_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


# ═══════════════════════════════════════════════════
# Колонки (статусы)
# ═══════════════════════════════════════════════════

@router.get("/task-statuses", response_model=list[TaskStatusOut])
async def list_task_statuses(project_id: int, db: AsyncSession = Depends(get_db)):
    await _get_project(project_id, db)
    result = await db.execute(
        select(TaskStatus)
        .where(TaskStatus.project_id == project_id)
        .order_by(TaskStatus.sort_order.asc(), TaskStatus.created_at.asc())
    )
    return result.scalars().all()


@router.post("/task-statuses", response_model=TaskStatusOut, status_code=201)
async def create_task_status(
    project_id: int,
    data: TaskStatusCreate,
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, db)
    max_order = await db.execute(
        select(TaskStatus.sort_order)
        .where(TaskStatus.project_id == project_id)
        .order_by(TaskStatus.sort_order.desc())
        .limit(1)
    )
    max_val = max_order.scalar_one_or_none() or 0
    status = TaskStatus(
        project_id=project_id,
        name=data.name,
        color=data.color or "#a78bfa",
        sort_order=max_val + 1,
    )
    db.add(status)
    await db.commit()
    await db.refresh(status)
    return status


@router.patch("/task-statuses/reorder", status_code=204)
async def reorder_task_statuses(
    project_id: int,
    data: TaskStatusReorderRequest,
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, db)
    for idx, status_id in enumerate(data.status_ids):
        await db.execute(
            update(TaskStatus)
            .where(TaskStatus.id == status_id, TaskStatus.project_id == project_id)
            .values(sort_order=idx)
        )
    await db.commit()
    return None


@router.patch("/task-statuses/{status_id}", response_model=TaskStatusOut)
async def update_task_status(
    project_id: int,
    status_id: int,
    data: TaskStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    status = await _get_status(project_id, status_id, db)
    if data.name is not None:
        status.name = data.name
    if data.color is not None:
        status.color = data.color
    status.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(status)
    return status


@router.delete("/task-statuses/{status_id}", status_code=204)
async def delete_task_status(
    project_id: int,
    status_id: int,
    db: AsyncSession = Depends(get_db),
):
    status = await _get_status(project_id, status_id, db)
    await db.delete(status)
    await db.commit()
    return None


# ═══════════════════════════════════════════════════
# Задачи
# ═══════════════════════════════════════════════════

@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(project_id: int, db: AsyncSession = Depends(get_db)):
    await _get_project(project_id, db)
    result = await db.execute(
        select(Task)
        .options(selectinload(Task.status), selectinload(Task.attachments))
        .where(Task.project_id == project_id)
        .order_by(Task.sort_order.asc(), Task.created_at.asc())
    )
    return result.scalars().all()


@router.get("/tasks/board", response_model=KanbanBoardOut)
async def get_kanban_board(
    project_id: int,
    priority: Optional[str] = None,
    assignee_email: Optional[str] = None,
    tags: Optional[str] = None,
    created_after: Optional[datetime] = None,
    created_before: Optional[datetime] = None,
    due_after: Optional[datetime] = None,
    due_before: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, db)
    statuses_result = await db.execute(
        select(TaskStatus)
        .where(TaskStatus.project_id == project_id)
        .order_by(TaskStatus.sort_order.asc(), TaskStatus.created_at.asc())
    )
    statuses = statuses_result.scalars().all()

    tasks_query = (
        select(Task)
        .options(selectinload(Task.status), selectinload(Task.attachments))
        .where(Task.project_id == project_id)
    )
    if priority is not None:
        tasks_query = tasks_query.where(Task.priority == priority)
    if assignee_email is not None:
        tasks_query = tasks_query.where(Task.assignee_email.ilike(f"%{assignee_email}%"))
    if tags is not None:
        tasks_query = tasks_query.where(Task.tags.ilike(f"%{tags}%"))
    if created_after is not None:
        tasks_query = tasks_query.where(Task.created_at >= created_after)
    if created_before is not None:
        tasks_query = tasks_query.where(Task.created_at <= created_before)
    if due_after is not None:
        tasks_query = tasks_query.where(Task.due_date >= due_after)
    if due_before is not None:
        tasks_query = tasks_query.where(Task.due_date <= due_before)

    tasks_result = await db.execute(
        tasks_query.order_by(Task.sort_order.asc(), Task.created_at.asc())
    )
    tasks = tasks_result.scalars().all()

    return KanbanBoardOut(statuses=statuses, tasks=tasks)


@router.get("/kanban/filters", response_model=KanbanFiltersOut)
async def project_kanban_filters(project_id: int, db: AsyncSession = Depends(get_db)):
    """Доступные значения фильтров для канбана проекта."""
    await _get_project(project_id, db)

    priorities_result = await db.execute(
        select(distinct(Task.priority))
        .where(Task.priority.isnot(None), Task.project_id == project_id)
    )
    priorities = [p[0] for p in priorities_result.fetchall() if p[0]]

    assignees_result = await db.execute(select(Assignee).order_by(Assignee.name.asc()))
    assignees = assignees_result.scalars().all()

    tags_result = await db.execute(
        select(Task.tags).where(Task.tags.isnot(None), Task.project_id == project_id)
    )
    tag_set = set()
    for (tags_str,) in tags_result.fetchall():
        for tag in tags_str.split(","):
            tag = tag.strip()
            if tag:
                tag_set.add(tag)

    return KanbanFiltersOut(
        projects=[],
        priorities=sorted(priorities),
        assignees=assignees,
        tags=sorted(tag_set),
    )


@router.post("/tasks", response_model=TaskOut, status_code=201)
async def create_task(
    project_id: int,
    data: TaskCreate,
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, db)
    await _get_status(project_id, data.status_id, db)

    max_order = await db.execute(
        select(Task.sort_order)
        .where(Task.project_id == project_id, Task.status_id == data.status_id)
        .order_by(Task.sort_order.desc())
        .limit(1)
    )
    max_val = max_order.scalar_one_or_none() or 0

    task = Task(
        project_id=project_id,
        status_id=data.status_id,
        title=data.title,
        description=data.description,
        priority=data.priority or "medium",
        due_date=data.due_date,
        assignee_email=data.assignee_email,
        tags=data.tags,
        sort_order=max_val + 1,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


@router.patch("/tasks/reorder", status_code=204)
async def reorder_tasks(
    project_id: int,
    data: TaskReorderRequest,
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, db)
    await _get_status(project_id, data.status_id, db)
    for idx, task_id in enumerate(data.task_ids):
        await db.execute(
            update(Task)
            .where(Task.id == task_id, Task.project_id == project_id)
            .values(status_id=data.status_id, sort_order=idx)
        )
    await db.commit()
    return None


@router.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task(
    project_id: int,
    task_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await _get_task(project_id, task_id, db)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    project_id: int,
    task_id: int,
    data: TaskUpdate,
    db: AsyncSession = Depends(get_db),
):
    task = await _get_task(project_id, task_id, db)
    update_data = data.model_dump(exclude_unset=True)
    if "status_id" in update_data:
        await _get_status(project_id, update_data["status_id"], db)
        task.status_id = update_data["status_id"]
    if "title" in update_data:
        task.title = update_data["title"]
    if "priority" in update_data:
        task.priority = update_data["priority"]
    if "description" in update_data:
        task.description = update_data["description"]
    if "due_date" in update_data:
        task.due_date = update_data["due_date"]
    if "assignee_email" in update_data:
        task.assignee_email = update_data["assignee_email"]
    if "tags" in update_data:
        task.tags = update_data["tags"]
    task.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(task)
    return task


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(
    project_id: int,
    task_id: int,
    db: AsyncSession = Depends(get_db),
):
    task = await _get_task(project_id, task_id, db)
    await db.delete(task)
    await db.commit()
    return None


# ═══════════════════════════════════════════════════
# Вложения к задачам (файлы, ссылки, git)
# ═══════════════════════════════════════════════════


def _task_uploads_dir() -> Path:
    settings = get_settings()
    base = Path(settings.local_storage_path).resolve()
    uploads = base / "tasks"
    uploads.mkdir(parents=True, exist_ok=True)
    return uploads


@router.post("/tasks/{task_id}/attachments", response_model=TaskAttachmentOut, status_code=201)
async def add_task_attachment(
    project_id: int,
    task_id: int,
    data: TaskAttachmentCreate,
    db: AsyncSession = Depends(get_db),
):
    task = await _get_task(project_id, task_id, db)
    attachment = TaskAttachment(
        task_id=task.id,
        attachment_type=data.attachment_type,
        title=data.title,
        url=data.url,
        file_path=data.file_path,
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)
    return attachment


@router.post("/tasks/{task_id}/attachments/upload", response_model=TaskAttachmentOut, status_code=201)
async def upload_task_attachment_file(
    project_id: int,
    task_id: int,
    title: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    task = await _get_task(project_id, task_id, db)
    if not file.filename:
        raise HTTPException(status_code=400, detail="File name is required")

    uploads_dir = _task_uploads_dir()
    ext = Path(file.filename).suffix
    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = uploads_dir / unique_name

    contents = await file.read()
    with open(file_path, "wb") as f:
        f.write(contents)

    rel_path = f"tasks/{unique_name}"
    attachment = TaskAttachment(
        task_id=task.id,
        attachment_type="file",
        title=title or file.filename,
        file_path=rel_path,
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)
    return attachment


@router.delete("/tasks/{task_id}/attachments/{attachment_id}", status_code=204)
async def delete_task_attachment(
    project_id: int,
    task_id: int,
    attachment_id: int,
    db: AsyncSession = Depends(get_db),
):
    task = await _get_task(project_id, task_id, db)
    result = await db.execute(
        select(TaskAttachment).where(
            TaskAttachment.id == attachment_id,
            TaskAttachment.task_id == task.id,
        )
    )
    attachment = result.scalar_one_or_none()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    if attachment.attachment_type == "file" and attachment.file_path:
        try:
            full_path = Path(get_settings().local_storage_path).resolve() / attachment.file_path
            if full_path.exists():
                full_path.unlink()
        except OSError:
            pass

    await db.delete(attachment)
    await db.commit()
    return None


@router.get("/tasks/{task_id}/attachments/{attachment_id}/collabora")
async def collabora_task_attachment(
    project_id: int,
    task_id: int,
    attachment_id: int,
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    """Вернуть URL iframe для редактирования вложения задачи в Collabora Online."""
    if not settings.collabora_enabled:
        raise HTTPException(status_code=503, detail="Collabora Online is not enabled")

    task = await _get_task(project_id, task_id, db)
    result = await db.execute(
        select(TaskAttachment).where(
            TaskAttachment.id == attachment_id,
            TaskAttachment.task_id == task.id,
        )
    )
    attachment = result.scalar_one_or_none()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    if attachment.attachment_type != "file" or not attachment.file_path:
        raise HTTPException(status_code=400, detail="Not a file attachment")

    ext = Path(attachment.title or attachment.file_path).suffix.lower()
    if ext not in OFFICE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file type for Collabora")

    local_path = await storage.get_local_path(attachment.file_path)
    if not local_path or not os.path.exists(local_path):
        raise HTTPException(status_code=400, detail="File is not available locally")

    file_id = encode_file_id(project_file_path=attachment.file_path)
    iframe_url = await build_collabora_iframe_url(file_id, ext, settings)
    return {
        "url": iframe_url,
        "wopi_src": f"{settings.collabora_wopi_internal_url.rstrip('/')}/wopi/files/{file_id}",
    }


@router.post("/tasks/{task_id}/attachments/{attachment_id}/open")
async def open_task_attachment(
    request: Request,
    project_id: int,
    task_id: int,
    attachment_id: int,
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
):
    """Открыть файл-вложение задачи в системном приложении. Только localhost."""
    task = await _get_task(project_id, task_id, db)
    result = await db.execute(
        select(TaskAttachment).where(
            TaskAttachment.id == attachment_id,
            TaskAttachment.task_id == task.id,
        )
    )
    attachment = result.scalar_one_or_none()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    if attachment.attachment_type != "file" or not attachment.file_path:
        raise HTTPException(status_code=400, detail="Not a file attachment")

    client_host = request.client.host if request.client else None
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=403, detail="Remote open not allowed")

    local_path = await storage.get_local_path(attachment.file_path)
    if not local_path or not os.path.exists(local_path):
        raise HTTPException(status_code=404, detail="File not found")

    def _get_gui_env():
        env = os.environ.copy()
        uid = str(os.getuid())
        runtime_dir = f"/run/user/{uid}"
        env["XDG_RUNTIME_DIR"] = runtime_dir
        env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={runtime_dir}/bus"
        display = None
        try:
            result = subprocess.run(
                ["pgrep", "-a", "-u", uid, "-f", "Xwayland|Xorg"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split()
                for i, part in enumerate(parts):
                    if part in ("Xwayland", "Xorg") and i + 1 < len(parts):
                        candidate = parts[i + 1]
                        if candidate.startswith(":"):
                            display = candidate
                            break
                if display:
                    break
        except Exception:
            pass
        if not display:
            try:
                result = subprocess.run(
                    ["ps", "e", "-u", uid],
                    capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.split("\n"):
                    if "DISPLAY=:" in line:
                        for part in line.split():
                            if part.startswith("DISPLAY=:"):
                                display = part.split("=", 1)[1]
                                break
                    if display:
                        break
            except Exception:
                pass
        if display:
            env["DISPLAY"] = display

        xauthority = None
        try:
            result = subprocess.run(
                ["ps", "e", "-u", uid],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.split("\n"):
                if "XAUTHORITY=" in line:
                    for part in line.split():
                        if part.startswith("XAUTHORITY="):
                            xauthority = part.split("=", 1)[1]
                            break
                if xauthority:
                    break
        except Exception:
            pass
        if xauthority:
            env["XAUTHORITY"] = xauthority

        return env

    system = platform.system()
    try:
        if system == "Windows":
            os.startfile(local_path)
        elif system == "Darwin":
            subprocess.Popen(["open", local_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            gui_env = _get_gui_env()
            subprocess.Popen(
                ["xdg-open", local_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=gui_env,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open file: {str(e)}")

    return {"status": "opened", "path": local_path}


# ═══════════════════════════════════════════════════
# Экспорт / импорт канбана проекта
# ═══════════════════════════════════════════════════

async def _build_project_export(project_id: int, db: AsyncSession) -> dict:
    """Собрать данные для экспорта одного проекта."""
    project = await _get_project(project_id, db)

    statuses_result = await db.execute(
        select(TaskStatus)
        .where(TaskStatus.project_id == project_id)
        .order_by(TaskStatus.sort_order.asc(), TaskStatus.created_at.asc())
    )
    statuses = statuses_result.scalars().all()

    tasks_result = await db.execute(
        select(Task)
        .options(selectinload(Task.attachments))
        .where(Task.project_id == project_id)
        .order_by(Task.sort_order.asc(), Task.created_at.asc())
    )
    tasks = tasks_result.scalars().all()

    status_map = {s.id: s.name for s in statuses}

    return {
        "name": project.name,
        "description": project.description,
        "statuses": [
            {
                "name": s.name,
                "color": s.color,
                "sort_order": s.sort_order,
            }
            for s in statuses
        ],
        "tasks": [
            {
                "title": t.title,
                "description": t.description,
                "priority": t.priority,
                "due_date": t.due_date,
                "assignee_email": t.assignee_email,
                "tags": t.tags,
                "sort_order": t.sort_order,
                "status_name": status_map.get(t.status_id, ""),
                "attachments": [
                    {
                        "attachment_type": a.attachment_type,
                        "title": a.title,
                        "url": a.url,
                        "file_path": a.file_path,
                    }
                    for a in t.attachments
                ],
            }
            for t in tasks
        ],
    }


async def _import_project_data(
    project_id: int,
    project_data: KanbanProjectExport,
    db: AsyncSession,
) -> tuple[int, int]:
    """Импортировать статусы и задачи в указанный проект."""
    imported_statuses = 0
    imported_tasks = 0

    status_name_to_id = {}
    for status_data in project_data.statuses:
        status_result = await db.execute(
            select(TaskStatus).where(
                TaskStatus.project_id == project_id,
                TaskStatus.name == status_data.name,
            )
        )
        status = status_result.scalar_one_or_none()
        if not status:
            status = TaskStatus(
                project_id=project_id,
                name=status_data.name,
                color=status_data.color,
                sort_order=status_data.sort_order,
            )
            db.add(status)
            await db.flush()
            await db.refresh(status)
            imported_statuses += 1
        else:
            status.color = status_data.color
            status.sort_order = status_data.sort_order
        status_name_to_id[status.name] = status.id

    for task_data in project_data.tasks:
        status_id = status_name_to_id.get(task_data.status_name)
        if not status_id:
            status_result = await db.execute(
                select(TaskStatus).where(
                    TaskStatus.project_id == project_id,
                    TaskStatus.name == task_data.status_name,
                )
            )
            status = status_result.scalar_one_or_none()
            if not status:
                continue
            status_id = status.id

        task_result = await db.execute(
            select(Task).where(
                Task.project_id == project_id,
                Task.title == task_data.title,
                Task.status_id == status_id,
            )
        )
        task = task_result.scalar_one_or_none()
        if not task:
            task = Task(
                project_id=project_id,
                status_id=status_id,
                title=task_data.title,
                description=task_data.description,
                priority=task_data.priority,
                due_date=task_data.due_date,
                assignee_email=task_data.assignee_email,
                tags=task_data.tags,
                sort_order=task_data.sort_order,
            )
            db.add(task)
            imported_tasks += 1
        else:
            task.description = task_data.description
            task.priority = task_data.priority
            task.due_date = task_data.due_date
            task.assignee_email = task_data.assignee_email
            task.tags = task_data.tags
            task.sort_order = task_data.sort_order

        await db.flush()
        await db.refresh(task)

        attachments_to_import = list(task_data.attachments or [])
        if attachments_to_import:
            old_attachments_result = await db.execute(
                select(TaskAttachment).where(TaskAttachment.task_id == task.id)
            )
            for old in old_attachments_result.scalars().all():
                if old.attachment_type == "file" and old.file_path:
                    try:
                        full_path = Path(get_settings().local_storage_path).resolve() / old.file_path
                        if full_path.exists():
                            full_path.unlink()
                    except OSError:
                        pass
                await db.delete(old)

            for attachment_data in attachments_to_import:
                attachment = TaskAttachment(
                    task_id=task.id,
                    attachment_type=attachment_data.attachment_type,
                    title=attachment_data.title,
                    url=attachment_data.url,
                    file_path=attachment_data.file_path,
                )
                db.add(attachment)

    return imported_statuses, imported_tasks


@router.get("/kanban/export", response_model=KanbanExportOut)
async def export_project_kanban(project_id: int, db: AsyncSession = Depends(get_db)):
    """Экспорт колонок и задач канбана конкретного проекта."""
    project_export = await _build_project_export(project_id, db)
    return {
        "version": 1,
        "exported_at": datetime.utcnow(),
        "projects": [project_export],
    }


@router.post("/kanban/import")
async def import_project_kanban(
    project_id: int,
    data: KanbanImportIn,
    db: AsyncSession = Depends(get_db),
):
    """Импорт колонок и задач канбана в конкретный проект."""
    await _get_project(project_id, db)

    imported_statuses = 0
    imported_tasks = 0

    for project_data in data.projects:
        statuses, tasks = await _import_project_data(project_id, project_data, db)
        imported_statuses += statuses
        imported_tasks += tasks

    await db.commit()
    return {
        "success": True,
        "imported_statuses": imported_statuses,
        "imported_tasks": imported_tasks,
    }


# ═══════════════════════════════════════════════════
# Общий канбан
# ═══════════════════════════════════════════════════

@global_router.get("/kanban", response_model=KanbanGlobalOut)
async def global_kanban(
    project_id: Optional[int] = None,
    priority: Optional[str] = None,
    assignee_email: Optional[str] = None,
    tags: Optional[str] = None,
    created_after: Optional[datetime] = None,
    created_before: Optional[datetime] = None,
    due_after: Optional[datetime] = None,
    due_before: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    """Все задачи всех проектов с фильтрами для общего канбана."""
    query = select(Task).options(selectinload(Task.status), selectinload(Task.attachments))

    if project_id is not None:
        query = query.where(Task.project_id == project_id)
    if priority is not None:
        query = query.where(Task.priority == priority)
    if assignee_email is not None:
        query = query.where(Task.assignee_email.ilike(f"%{assignee_email}%"))
    if tags is not None:
        query = query.where(Task.tags.ilike(f"%{tags}%"))
    if created_after is not None:
        query = query.where(Task.created_at >= created_after)
    if created_before is not None:
        query = query.where(Task.created_at <= created_before)
    if due_after is not None:
        query = query.where(Task.due_date >= due_after)
    if due_before is not None:
        query = query.where(Task.due_date <= due_before)

    result = await db.execute(query.order_by(Task.sort_order.asc(), Task.created_at.asc()))
    tasks = result.scalars().all()

    # Колонки — уникальные названия статусов с приоритетным цветом (самый частый)
    color_query = select(TaskStatus.name, TaskStatus.color, func.count(TaskStatus.id).label("cnt"))
    if project_id is not None:
        color_query = color_query.where(TaskStatus.project_id == project_id)
    color_query = color_query.group_by(TaskStatus.name, TaskStatus.color)
    color_result = await db.execute(color_query)

    column_colors = {}
    for name, color, cnt in color_result.fetchall():
        if name not in column_colors or cnt > column_colors[name]["cnt"]:
            column_colors[name] = {"color": color, "cnt": cnt}

    # Порядок колонок определяется минимальным sort_order среди статусов с таким именем
    order_query = select(TaskStatus.name, func.min(TaskStatus.sort_order).label("min_order"))
    if project_id is not None:
        order_query = order_query.where(TaskStatus.project_id == project_id)
    order_query = order_query.group_by(TaskStatus.name)
    order_result = await db.execute(order_query)
    column_order = {name: min_order for name, min_order in order_result.fetchall()}

    columns = [KanbanColumnOut(name=name, color=data["color"]) for name, data in column_colors.items()]
    columns.sort(key=lambda c: (column_order.get(c.name, 0), c.name))

    return KanbanGlobalOut(columns=columns, tasks=tasks)


@global_router.get("/kanban/filters", response_model=KanbanFiltersOut)
async def global_kanban_filters(db: AsyncSession = Depends(get_db)):
    """Доступные значения фильтров для общего канбана."""
    projects_result = await db.execute(select(Project).order_by(Project.name.asc()))
    projects = projects_result.scalars().all()

    priorities_result = await db.execute(select(distinct(Task.priority)).where(Task.priority.isnot(None)))
    priorities = [p[0] for p in priorities_result.fetchall() if p[0]]

    assignees_result = await db.execute(select(Assignee).order_by(Assignee.name.asc()))
    assignees = assignees_result.scalars().all()

    tags_result = await db.execute(select(Task.tags).where(Task.tags.isnot(None)))
    tag_set = set()
    for (tags_str,) in tags_result.fetchall():
        for tag in tags_str.split(","):
            tag = tag.strip()
            if tag:
                tag_set.add(tag)

    return KanbanFiltersOut(
        projects=projects,
        priorities=sorted(priorities),
        assignees=assignees,
        tags=sorted(tag_set),
    )


@global_router.get("/kanban/columns", response_model=list[KanbanColumnOut])
async def list_global_kanban_columns(db: AsyncSession = Depends(get_db)):
    """Уникальные колонки общего канбана с самым частым цветом."""
    color_query = select(TaskStatus.name, TaskStatus.color, func.count(TaskStatus.id).label("cnt")).group_by(
        TaskStatus.name, TaskStatus.color
    )
    color_result = await db.execute(color_query)

    column_colors = {}
    for name, color, cnt in color_result.fetchall():
        if name not in column_colors or cnt > column_colors[name]["cnt"]:
            column_colors[name] = {"color": color, "cnt": cnt}

    order_query = select(TaskStatus.name, func.min(TaskStatus.sort_order).label("min_order")).group_by(
        TaskStatus.name
    )
    order_result = await db.execute(order_query)
    column_order = {name: min_order for name, min_order in order_result.fetchall()}

    columns = [KanbanColumnOut(name=name, color=data["color"]) for name, data in column_colors.items()]
    columns.sort(key=lambda c: (column_order.get(c.name, 0), c.name))
    return columns


@global_router.post("/kanban/columns", response_model=list[TaskStatusOut], status_code=201)
async def create_global_kanban_column(
    data: GlobalKanbanColumnCreate,
    db: AsyncSession = Depends(get_db),
):
    """Создать колонку с указанным именем во всех проектах, где её ещё нет."""
    projects_result = await db.execute(select(Project))
    projects = projects_result.scalars().all()
    if not projects:
        raise HTTPException(status_code=400, detail="No projects found")

    created = []
    for project in projects:
        existing = await db.execute(
            select(TaskStatus).where(TaskStatus.project_id == project.id, TaskStatus.name == data.name)
        )
        if existing.scalar_one_or_none():
            continue

        max_order = await db.execute(
            select(TaskStatus.sort_order)
            .where(TaskStatus.project_id == project.id)
            .order_by(TaskStatus.sort_order.desc())
            .limit(1)
        )
        max_val = max_order.scalar_one_or_none() or 0
        status = TaskStatus(
            project_id=project.id,
            name=data.name,
            color=data.color or "#a78bfa",
            sort_order=max_val + 1,
        )
        db.add(status)
        await db.flush()
        await db.refresh(status)
        created.append(status)

    await db.commit()
    return created


@global_router.patch("/kanban/columns/{name}", response_model=list[TaskStatusOut])
async def update_global_kanban_column(
    name: str,
    data: GlobalKanbanColumnUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Переименовать или перекрасить колонку во всех проектах."""
    result = await db.execute(select(TaskStatus).where(TaskStatus.name == name))
    statuses = result.scalars().all()
    if not statuses:
        raise HTTPException(status_code=404, detail="Column not found")

    new_name = data.new_name.strip() if data.new_name else None
    if new_name:
        for status in statuses:
            conflict = await db.execute(
                select(TaskStatus).where(
                    TaskStatus.project_id == status.project_id,
                    TaskStatus.name == new_name,
                    TaskStatus.id != status.id,
                )
            )
            if conflict.scalar_one_or_none():
                raise HTTPException(
                    status_code=400,
                    detail=f"Column '{new_name}' already exists in project",
                )
            status.name = new_name

    if data.color:
        for status in statuses:
            status.color = data.color

    await db.commit()
    for status in statuses:
        await db.refresh(status)
    return statuses


@global_router.delete("/kanban/columns/{name}", status_code=204)
async def delete_global_kanban_column(
    name: str,
    db: AsyncSession = Depends(get_db),
):
    """Удалить колонку во всех проектах, если в них нет задач."""
    result = await db.execute(select(TaskStatus).where(TaskStatus.name == name))
    statuses = result.scalars().all()
    if not statuses:
        raise HTTPException(status_code=404, detail="Column not found")

    for status in statuses:
        tasks_result = await db.execute(select(Task.id).where(Task.status_id == status.id).limit(1))
        if tasks_result.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"Column '{name}' has tasks in some projects",
            )

    for status in statuses:
        await db.delete(status)
    await db.commit()
    return None


@global_router.patch("/kanban/tasks/{task_id}/status", response_model=TaskOut)
async def update_task_status_by_column_name(
    task_id: int,
    data: KanbanTaskStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Обновить статус задачи, найдя статус проекта по названию колонки."""
    result = await db.execute(
        select(Task)
        .options(selectinload(Task.status), selectinload(Task.attachments))
        .where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    status_result = await db.execute(
        select(TaskStatus)
        .where(TaskStatus.project_id == task.project_id, TaskStatus.name == data.column_name)
        .order_by(TaskStatus.sort_order.asc())
        .limit(1)
    )
    status = status_result.scalar_one_or_none()
    if not status:
        raise HTTPException(
            status_code=400,
            detail=f"Status '{data.column_name}' not found in project"
        )

    task.status_id = status.id
    task.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(task)
    return task


@global_router.get("/kanban/export", response_model=KanbanExportOut)
async def export_global_kanban(db: AsyncSession = Depends(get_db)):
    """Экспорт всех колонок и задач канбана по проектам."""
    projects_result = await db.execute(select(Project).order_by(Project.name.asc()))
    projects = projects_result.scalars().all()

    export_projects = []
    for project in projects:
        export_projects.append(await _build_project_export(project.id, db))

    return {
        "version": 1,
        "exported_at": datetime.utcnow(),
        "projects": export_projects,
    }


@global_router.post("/kanban/import")
async def import_global_kanban(
    data: KanbanImportIn,
    db: AsyncSession = Depends(get_db),
):
    """Импорт колонок и задач канбана из JSON-дампа."""
    imported_projects = 0
    imported_statuses = 0
    imported_tasks = 0

    for project_data in data.projects:
        project_result = await db.execute(
            select(Project).where(Project.name == project_data.name)
        )
        project = project_result.scalar_one_or_none()
        if not project:
            project = Project(
                name=project_data.name,
                description=project_data.description,
            )
            db.add(project)
            await db.flush()
            await db.refresh(project)
        imported_projects += 1

        statuses, tasks = await _import_project_data(project.id, project_data, db)
        imported_statuses += statuses
        imported_tasks += tasks

    await db.commit()
    return {
        "success": True,
        "imported_projects": imported_projects,
        "imported_statuses": imported_statuses,
        "imported_tasks": imported_tasks,
    }
