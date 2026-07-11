from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.config import get_settings
from app.markdown import render_markdown
from app.pocketbase_client import (
    PocketBaseClient,
    _log_activity,
    ensure_project_comments_collection,
    get_current_user,
    pb_client,
)

router = APIRouter(prefix="/api/pocketbase", tags=["pocketbase"])


def get_pb_client() -> PocketBaseClient:
    return pb_client


class CommentCreate(BaseModel):
    text: str
    parent_id: str | None = None


class CommentUpdate(BaseModel):
    text: str


class CommentOut(BaseModel):
    id: str
    project_id: int
    user_email: str
    user_name: str
    text: str
    text_html: str
    parent_id: str | None
    created: str
    updated: str


class ActivityOut(BaseModel):
    id: str
    project_id: int
    user_email: str
    user_name: str
    action: str
    entity_type: str
    entity_id: str
    description: str
    created: str
    updated: str


def _comment_out(item: dict[str, Any]) -> dict[str, Any]:
    text = item.get("text") or ""
    return {
        "id": item.get("id"),
        "project_id": item.get("project_id"),
        "user_email": item.get("user_email"),
        "user_name": item.get("user_name") or item.get("user_email"),
        "text": text,
        "text_html": render_markdown(text),
        "parent_id": item.get("parent_id") or None,
        "created": item.get("created") or "",
        "updated": item.get("updated") or "",
    }


def _activity_out(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "project_id": item.get("project_id"),
        "user_email": item.get("user_email"),
        "user_name": item.get("user_name") or item.get("user_email"),
        "action": item.get("action") or "",
        "entity_type": item.get("entity_type") or "",
        "entity_id": item.get("entity_id") or "",
        "description": item.get("description") or "",
        "created": item.get("created") or "",
        "updated": item.get("updated") or "",
    }


async def _get_comment(
    client: PocketBaseClient, project_id: int, comment_id: str
) -> dict[str, Any]:
    """Получить комментарий проекта по id."""
    items = await client.list_records(
        "project_comments",
        filter_expr=f'id="{comment_id}" && project_id={project_id}',
    )
    if not items:
        raise HTTPException(status_code=404, detail="Комментарий не найден")
    return items[0]


@router.get("/projects/{project_id}/comments", response_model=list[CommentOut])
async def list_comments(
    project_id: int,
    since: str | None = None,
    client: PocketBaseClient = Depends(get_pb_client),
):
    settings = get_settings()
    if not settings.pocketbase_enabled:
        raise HTTPException(status_code=503, detail="PocketBase отключён")
    await ensure_project_comments_collection()
    # Хронологический порядок для удобного отображения threads
    filter_expr = f"project_id={project_id}"
    if since:
        filter_expr += f" && updated >= '{since}'"
    items = await client.list_records(
        "project_comments",
        filter_expr=filter_expr,
        sort="created",
    )
    return [_comment_out(item) for item in items]


@router.post("/projects/{project_id}/comments", response_model=CommentOut)
async def create_comment(
    project_id: int,
    data: CommentCreate,
    request: Request,
    client: PocketBaseClient = Depends(get_pb_client),
):
    settings = get_settings()
    if not settings.pocketbase_enabled:
        raise HTTPException(status_code=503, detail="PocketBase отключён")
    if not data.text.strip():
        raise HTTPException(status_code=400, detail="Текст комментария не может быть пустым")

    await ensure_project_comments_collection()
    user = get_current_user(request)
    payload: dict[str, Any] = {
        "project_id": project_id,
        "user_email": user["email"],
        "user_name": user["name"],
        "text": data.text.strip(),
    }
    if data.parent_id:
        payload["parent_id"] = data.parent_id

    record = await client.create_record("project_comments", payload)
    if not record:
        raise HTTPException(status_code=500, detail="Не удалось создать комментарий")

    if record.get("project_id") is None or record.get("text") is None:
        raise HTTPException(
            status_code=500,
            detail="Коллекция project_comments в PocketBase настроена неверно. Удалите её в админке и перезапустите ARMory.",
        )

    await _log_activity(
        project_id,
        user,
        "create",
        "comment",
        record["id"],
        "Добавил комментарий",
    )

    return _comment_out(record)


@router.patch("/projects/{project_id}/comments/{comment_id}", response_model=CommentOut)
async def update_comment(
    project_id: int,
    comment_id: str,
    data: CommentUpdate,
    request: Request,
    client: PocketBaseClient = Depends(get_pb_client),
):
    settings = get_settings()
    if not settings.pocketbase_enabled:
        raise HTTPException(status_code=503, detail="PocketBase отключён")
    if not data.text.strip():
        raise HTTPException(status_code=400, detail="Текст комментария не может быть пустым")

    await ensure_project_comments_collection()
    comment = await _get_comment(client, project_id, comment_id)
    user = get_current_user(request)
    if comment.get("user_email") != user["email"]:
        raise HTTPException(status_code=403, detail="Нельзя редактировать чужой комментарий")

    record = await client.update_record(
        "project_comments",
        comment_id,
        {"text": data.text.strip()},
    )
    if not record:
        raise HTTPException(status_code=500, detail="Не удалось обновить комментарий")

    await _log_activity(
        project_id,
        user,
        "update",
        "comment",
        comment_id,
        "Изменил комментарий",
    )

    return _comment_out(record)


@router.delete("/projects/{project_id}/comments/{comment_id}")
async def delete_comment(
    project_id: int,
    comment_id: str,
    request: Request,
    client: PocketBaseClient = Depends(get_pb_client),
):
    settings = get_settings()
    if not settings.pocketbase_enabled:
        raise HTTPException(status_code=503, detail="PocketBase отключён")

    comment = await _get_comment(client, project_id, comment_id)
    user = get_current_user(request)
    if comment.get("user_email") != user["email"]:
        raise HTTPException(status_code=403, detail="Нельзя удалить чужой комментарий")

    ok = await client.delete_record("project_comments", comment_id)
    if not ok:
        raise HTTPException(status_code=500, detail="Не удалось удалить комментарий")

    await _log_activity(
        project_id,
        user,
        "delete",
        "comment",
        comment_id,
        "Удалил комментарий",
    )

    return {"message": "Комментарий удалён"}


@router.get("/projects/{project_id}/activity", response_model=list[ActivityOut])
async def list_activity(
    project_id: int,
    limit: int = 50,
    client: PocketBaseClient = Depends(get_pb_client),
):
    settings = get_settings()
    if not settings.pocketbase_enabled:
        raise HTTPException(status_code=503, detail="PocketBase отключён")
    from app.pocketbase_client import ensure_project_activity_collection

    await ensure_project_activity_collection()
    items = await client.list_records(
        "project_activity",
        filter_expr=f"project_id={project_id}",
        sort="-created",
    )
    return [_activity_out(item) for item in items[:limit]]
