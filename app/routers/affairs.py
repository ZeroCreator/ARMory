import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Affair, CalendarEvent, Project, ProjectComment
from app.routers.comments import _get_current_email


router = APIRouter(prefix="/api/affairs", tags=["affairs"])


class AffairCreate(BaseModel):
    title: str
    description: str | None = None
    due_date: datetime.datetime | None = None
    project_id: int | None = None


class AffairUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    due_date: datetime.datetime | None = None
    project_id: int | None = None
    is_completed: bool | None = None


def _affair_out(affair: Affair) -> dict:
    return {
        "id": affair.id,
        "project_id": affair.project_id,
        "project_name": affair.project.name if affair.project else None,
        "title": affair.title,
        "description": affair.description,
        "due_date": affair.due_date.isoformat() if affair.due_date else None,
        "is_completed": affair.is_completed,
        "created_at": affair.created_at.isoformat(),
        "updated_at": affair.updated_at.isoformat(),
    }


async def _validate_project(project_id: int | None, db: AsyncSession) -> None:
    if project_id is None:
        return
    result = await db.execute(select(Project.id).where(Project.id == project_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Проект не найден")


@router.get("/overview")
async def overview(request: Request, db: AsyncSession = Depends(get_db)):
    user_email = _get_current_email(request)
    projects_result = await db.execute(select(Project).order_by(Project.sort_order, Project.name))
    comments_result = await db.execute(
        select(ProjectComment)
        .where(ProjectComment.author_email == user_email)
        .order_by(ProjectComment.created_at.desc())
    )
    events_result = await db.execute(
        select(CalendarEvent).order_by(CalendarEvent.start_date.asc())
    )
    projects = projects_result.scalars().all()
    project_names = {project.id: project.name for project in projects}

    return {
        "user_email": user_email,
        "projects": [{"id": project.id, "name": project.name} for project in projects],
        "comments": [
            {
                "id": comment.id,
                "project_id": comment.project_id,
                "project_name": project_names.get(comment.project_id),
                "content": comment.content,
                "created_at": comment.created_at.isoformat(),
            }
            for comment in comments_result.scalars().all()
        ],
        "events": [
            {
                "id": event.id,
                "project_id": event.project_id,
                "project_name": project_names.get(event.project_id),
                "title": event.title,
                "description": event.description,
                "start_date": event.start_date.isoformat(),
                "end_date": event.end_date.isoformat() if event.end_date else None,
                "all_day": event.all_day,
                "color": event.color,
            }
            for event in events_result.scalars().all()
        ],
    }


@router.get("")
async def list_affairs(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Affair)
        .where(Affair.owner_email == _get_current_email(request))
        .options(selectinload(Affair.project))
        .order_by(Affair.is_completed, Affair.due_date.asc(), Affair.created_at.desc())
    )
    return [_affair_out(affair) for affair in result.scalars().all()]


@router.post("", status_code=201)
async def create_affair(data: AffairCreate, request: Request, db: AsyncSession = Depends(get_db)):
    title = data.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Название обязательно")
    await _validate_project(data.project_id, db)
    affair = Affair(
        owner_email=_get_current_email(request),
        title=title,
        description=data.description.strip() if data.description else None,
        due_date=data.due_date,
        project_id=data.project_id,
    )
    db.add(affair)
    await db.commit()
    result = await db.execute(
        select(Affair).where(Affair.id == affair.id).options(selectinload(Affair.project))
    )
    return _affair_out(result.scalar_one())


@router.patch("/{affair_id}")
async def update_affair(
    affair_id: int,
    data: AffairUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Affair).where(
            Affair.id == affair_id,
            Affair.owner_email == _get_current_email(request),
        )
    )
    affair = result.scalar_one_or_none()
    if not affair:
        raise HTTPException(status_code=404, detail="Дело не найдено")
    values = data.model_dump(exclude_unset=True)
    if "title" in values:
        values["title"] = (values["title"] or "").strip()
        if not values["title"]:
            raise HTTPException(status_code=400, detail="Название обязательно")
    if "description" in values and values["description"]:
        values["description"] = values["description"].strip()
    if "project_id" in values:
        await _validate_project(values["project_id"], db)
    for field, value in values.items():
        setattr(affair, field, value)
    affair.updated_at = datetime.datetime.utcnow()
    await db.commit()
    result = await db.execute(
        select(Affair).where(Affair.id == affair.id).options(selectinload(Affair.project))
    )
    return _affair_out(result.scalar_one())


@router.delete("/{affair_id}", status_code=204)
async def delete_affair(affair_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Affair).where(
            Affair.id == affair_id,
            Affair.owner_email == _get_current_email(request),
        )
    )
    affair = result.scalar_one_or_none()
    if not affair:
        raise HTTPException(status_code=404, detail="Дело не найдено")
    await db.delete(affair)
    await db.commit()
    return None
