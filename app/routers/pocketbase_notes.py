from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.config import get_settings
from app.markdown import render_markdown
from app.pocketbase_client import (
    PocketBaseClient,
    _log_activity,
    ensure_project_notes_collection,
    get_current_user,
    pb_client,
)

router = APIRouter(prefix="/api/pocketbase/projects/{project_id}/notes", tags=["pocketbase-notes"])


def get_pb_client() -> PocketBaseClient:
    return pb_client


class NoteCreate(BaseModel):
    title: str
    content: str
    pinned: bool = False


class NoteUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    pinned: bool | None = None


class NoteOut(BaseModel):
    id: str
    project_id: int
    title: str
    content: str
    content_html: str
    user_email: str
    user_name: str
    pinned: bool
    created: str
    updated: str


def _note_out(item: dict[str, Any]) -> dict[str, Any]:
    content = item.get("content") or ""
    return {
        "id": item.get("id"),
        "project_id": item.get("project_id"),
        "title": item.get("title") or "",
        "content": content,
        "content_html": render_markdown(content),
        "user_email": item.get("user_email"),
        "user_name": item.get("user_name") or item.get("user_email"),
        "pinned": bool(item.get("pinned")),
        "created": item.get("created") or "",
        "updated": item.get("updated") or "",
    }


async def _get_note(
    client: PocketBaseClient, project_id: int, note_id: str
) -> dict[str, Any]:
    items = await client.list_records(
        "project_notes",
        filter_expr=f'id="{note_id}" && project_id={project_id}',
    )
    if not items:
        raise HTTPException(status_code=404, detail="Заметка не найдена")
    return items[0]


@router.get("", response_model=list[NoteOut])
async def list_notes(
    project_id: int,
    since: str | None = None,
    client: PocketBaseClient = Depends(get_pb_client),
):
    settings = get_settings()
    if not settings.pocketbase_enabled:
        raise HTTPException(status_code=503, detail="PocketBase отключён")
    await ensure_project_notes_collection()
    filter_expr = f"project_id={project_id}"
    if since:
        filter_expr += f" && updated >= '{since}'"
    items = await client.list_records(
        "project_notes",
        filter_expr=filter_expr,
        sort="-pinned,-updated",
    )
    return [_note_out(item) for item in items]


@router.post("", response_model=NoteOut)
async def create_note(
    project_id: int,
    data: NoteCreate,
    request: Request,
    client: PocketBaseClient = Depends(get_pb_client),
):
    settings = get_settings()
    if not settings.pocketbase_enabled:
        raise HTTPException(status_code=503, detail="PocketBase отключён")
    if not data.title.strip():
        raise HTTPException(status_code=400, detail="Название заметки не может быть пустым")

    await ensure_project_notes_collection()
    user = get_current_user(request)
    record = await client.create_record(
        "project_notes",
        {
            "project_id": project_id,
            "title": data.title.strip(),
            "content": data.content.strip(),
            "user_email": user["email"],
            "user_name": user["name"],
            "pinned": data.pinned,
        },
    )
    if not record:
        raise HTTPException(status_code=500, detail="Не удалось создать заметку")

    await _log_activity(
        project_id,
        user,
        "create",
        "note",
        record["id"],
        f"Добавил заметку «{record.get('title', '')}»",
    )

    return _note_out(record)


@router.patch("/{note_id}", response_model=NoteOut)
async def update_note(
    project_id: int,
    note_id: str,
    data: NoteUpdate,
    request: Request,
    client: PocketBaseClient = Depends(get_pb_client),
):
    settings = get_settings()
    if not settings.pocketbase_enabled:
        raise HTTPException(status_code=503, detail="PocketBase отключён")

    await ensure_project_notes_collection()
    note = await _get_note(client, project_id, note_id)
    user = get_current_user(request)
    if note.get("user_email") != user["email"]:
        raise HTTPException(status_code=403, detail="Нельзя редактировать чужую заметку")

    payload: dict[str, Any] = {}
    if data.title is not None:
        payload["title"] = data.title.strip()
    if data.content is not None:
        payload["content"] = data.content.strip()
    if data.pinned is not None:
        payload["pinned"] = data.pinned

    if not payload:
        raise HTTPException(status_code=400, detail="Нет данных для обновления")

    record = await client.update_record("project_notes", note_id, payload)
    if not record:
        raise HTTPException(status_code=500, detail="Не удалось обновить заметку")

    action_desc = "Изменил заметку"
    if payload.get("pinned") is True:
        action_desc = "Закрепил заметку"
    elif payload.get("pinned") is False:
        action_desc = "Открепил заметку"

    await _log_activity(
        project_id,
        user,
        "update",
        "note",
        note_id,
        action_desc,
    )

    return _note_out(record)


@router.delete("/{note_id}")
async def delete_note(
    project_id: int,
    note_id: str,
    request: Request,
    client: PocketBaseClient = Depends(get_pb_client),
):
    settings = get_settings()
    if not settings.pocketbase_enabled:
        raise HTTPException(status_code=503, detail="PocketBase отключён")

    note = await _get_note(client, project_id, note_id)
    user = get_current_user(request)
    if note.get("user_email") != user["email"]:
        raise HTTPException(status_code=403, detail="Нельзя удалить чужую заметку")

    ok = await client.delete_record("project_notes", note_id)
    if not ok:
        raise HTTPException(status_code=500, detail="Не удалось удалить заметку")

    await _log_activity(
        project_id,
        user,
        "delete",
        "note",
        note_id,
        f"Удалил заметку «{note.get('title', '')}»",
    )

    return {"message": "Заметка удалена"}
