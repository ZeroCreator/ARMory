from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.config import get_settings
from app.pocketbase_client import (
    PocketBaseClient,
    _log_activity,
    ensure_project_tasks_collection,
    get_current_user,
    pb_client,
)

router = APIRouter(prefix="/api/pocketbase/projects/{project_id}/tasks", tags=["pocketbase-tasks"])


def get_pb_client() -> PocketBaseClient:
    return pb_client


class TaskCreate(BaseModel):
    title: str
    assignee_email: str | None = None
    due_date: str | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    done: bool | None = None
    assignee_email: str | None = None
    due_date: str | None = None


class TaskReorderRequest(BaseModel):
    task_ids: list[str]


class TaskOut(BaseModel):
    id: str
    project_id: int
    title: str
    done: bool
    assignee_email: str | None
    due_date: str | None
    sort_order: int
    created: str
    updated: str


def _task_out(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "project_id": item.get("project_id"),
        "title": item.get("title") or "",
        "done": bool(item.get("done")),
        "assignee_email": item.get("assignee_email") or None,
        "due_date": item.get("due_date") or None,
        "sort_order": item.get("sort_order") or 0,
        "created": item.get("created") or "",
        "updated": item.get("updated") or "",
    }


async def _get_task(
    client: PocketBaseClient, project_id: int, task_id: str
) -> dict[str, Any]:
    items = await client.list_records(
        "project_tasks",
        filter_expr=f'id="{task_id}" && project_id={project_id}',
    )
    if not items:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return items[0]


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    project_id: int,
    since: str | None = None,
    client: PocketBaseClient = Depends(get_pb_client),
):
    settings = get_settings()
    if not settings.pocketbase_enabled:
        raise HTTPException(status_code=503, detail="PocketBase отключён")
    await ensure_project_tasks_collection()
    filter_expr = f"project_id={project_id}"
    if since:
        filter_expr += f" && updated >= '{since}'"
    items = await client.list_records(
        "project_tasks",
        filter_expr=filter_expr,
        sort="sort_order,created",
    )
    return [_task_out(item) for item in items]


@router.post("", response_model=TaskOut)
async def create_task(
    project_id: int,
    data: TaskCreate,
    request: Request,
    client: PocketBaseClient = Depends(get_pb_client),
):
    settings = get_settings()
    if not settings.pocketbase_enabled:
        raise HTTPException(status_code=503, detail="PocketBase отключён")
    if not data.title.strip():
        raise HTTPException(status_code=400, detail="Название задачи не может быть пустым")

    await ensure_project_tasks_collection()
    user = get_current_user(request)
    # sort_order = максимальный + 1
    existing = await client.list_records(
        "project_tasks",
        filter_expr=f"project_id={project_id}",
        sort="-sort_order",
        # pocketbase limit perPage default 30; достаточно для одного top
    )
    max_order = 0
    if existing:
        max_order = (existing[0].get("sort_order") or 0) + 1

    record = await client.create_record(
        "project_tasks",
        {
            "project_id": project_id,
            "title": data.title.strip(),
            "done": False,
            "assignee_email": data.assignee_email,
            "due_date": data.due_date,
            "sort_order": max_order,
        },
    )
    if not record:
        raise HTTPException(status_code=500, detail="Не удалось создать задачу")

    await _log_activity(
        project_id,
        user,
        "create",
        "task",
        record["id"],
        f"Добавил задачу «{record.get('title', '')}»",
    )

    return _task_out(record)


# Важно: /reorder должен быть ДО /{task_id}, иначе FastAPI примет "reorder" как task_id.
@router.patch("/reorder", response_model=dict)
async def reorder_tasks(
    project_id: int,
    data: TaskReorderRequest,
    request: Request,
    client: PocketBaseClient = Depends(get_pb_client),
):
    settings = get_settings()
    if not settings.pocketbase_enabled:
        raise HTTPException(status_code=503, detail="PocketBase отключён")
    await ensure_project_tasks_collection()

    errors = []
    for idx, task_id in enumerate(data.task_ids):
        record = await client.update_record(
            "project_tasks", task_id, {"sort_order": idx}
        )
        if not record:
            errors.append(task_id)

    if errors:
        raise HTTPException(status_code=500, detail=f"Не удалось обновить порядок: {errors}")

    return {"message": "Порядок задач обновлён"}


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(
    project_id: int,
    task_id: str,
    data: TaskUpdate,
    request: Request,
    client: PocketBaseClient = Depends(get_pb_client),
):
    settings = get_settings()
    if not settings.pocketbase_enabled:
        raise HTTPException(status_code=503, detail="PocketBase отключён")

    await ensure_project_tasks_collection()
    await _get_task(client, project_id, task_id)
    user = get_current_user(request)

    payload: dict[str, Any] = {}
    if data.title is not None:
        payload["title"] = data.title.strip()
    if data.done is not None:
        payload["done"] = data.done
    if data.assignee_email is not None:
        payload["assignee_email"] = data.assignee_email or None
    if data.due_date is not None:
        payload["due_date"] = data.due_date or None

    if not payload:
        raise HTTPException(status_code=400, detail="Нет данных для обновления")

    record = await client.update_record("project_tasks", task_id, payload)
    if not record:
        raise HTTPException(status_code=500, detail="Не удалось обновить задачу")

    action_desc = "Изменил задачу"
    if payload.get("done") is True:
        action_desc = f"Выполнил задачу «{record.get('title', '')}»"
    elif payload.get("done") is False:
        action_desc = f"Вернул задачу «{record.get('title', '')}» в работу"
    elif payload.get("assignee_email"):
        action_desc = f"Назначил ответственного для задачи «{record.get('title', '')}»"
    elif payload.get("assignee_email") is None:
        action_desc = f"Снял ответственного с задачи «{record.get('title', '')}»"

    await _log_activity(
        project_id,
        user,
        "update",
        "task",
        task_id,
        action_desc,
    )

    return _task_out(record)


@router.delete("/{task_id}")
async def delete_task(
    project_id: int,
    task_id: str,
    request: Request,
    client: PocketBaseClient = Depends(get_pb_client),
):
    settings = get_settings()
    if not settings.pocketbase_enabled:
        raise HTTPException(status_code=503, detail="PocketBase отключён")

    task = await _get_task(client, project_id, task_id)
    user = get_current_user(request)
    ok = await client.delete_record("project_tasks", task_id)
    if not ok:
        raise HTTPException(status_code=500, detail="Не удалось удалить задачу")

    await _log_activity(
        project_id,
        user,
        "delete",
        "task",
        task_id,
        f"Удалил задачу «{task.get('title', '')}»",
    )

    return {"message": "Задача удалена"}
