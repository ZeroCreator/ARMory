import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.config import get_settings
from app.models import Affair, CalendarEvent, DailyNewsRead, Project, ProjectComment, Task, TaskStatus
from app.routers.comments import _get_current_email


router = APIRouter(prefix="/api/affairs", tags=["affairs"])
settings = get_settings()


class AffairCreate(BaseModel):
    title: str
    description: str | None = None
    due_date: datetime.datetime | None = None
    project_id: int | None = None
    is_shared: bool | None = None
    show_in_news: bool = False


class AffairUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    due_date: datetime.datetime | None = None
    project_id: int | None = None
    is_completed: bool | None = None
    show_in_news: bool | None = None


def _affair_out(affair: Affair) -> dict:
    return {
        "id": affair.id,
        "project_id": affair.project_id,
        "project_name": affair.project.name if affair.project else None,
        "is_shared": affair.is_shared,
        "show_in_news": affair.show_in_news,
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
    now = datetime.datetime.now()
    projects_result = await db.execute(select(Project).order_by(Project.sort_order, Project.name))
    affairs_result = await db.execute(
        select(Affair)
        .where(Affair.is_shared.is_(True))
        .order_by(Affair.is_completed, Affair.updated_at.desc())
    )
    comments_result = await db.execute(
        select(ProjectComment)
        .where(ProjectComment.author_email == user_email)
        .order_by(ProjectComment.created_at.desc())
    )
    events_result = await db.execute(
        select(CalendarEvent)
        .where(
            or_(
                CalendarEvent.end_date >= now,
                and_(CalendarEvent.end_date.is_(None), CalendarEvent.start_date >= now),
            )
        )
        .order_by(CalendarEvent.start_date.asc())
    )
    projects = projects_result.scalars().all()
    project_names = {project.id: project.name for project in projects}

    return {
        "user_email": _get_current_email(request),
        "projects": [{"id": project.id, "name": project.name} for project in projects],
        "notes": [
            {
                "id": affair.id,
                "project_id": affair.project_id,
                "project_name": project_names.get(affair.project_id),
                "is_shared": affair.is_shared,
                "show_in_news": affair.show_in_news,
                "title": affair.title,
                "description": affair.description,
                "due_date": affair.due_date.isoformat() if affair.due_date else None,
                "is_completed": affair.is_completed,
                "updated_at": affair.updated_at.isoformat(),
            }
            for affair in affairs_result.scalars().all()
        ],
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


@router.get("/daily")
async def daily_news(request: Request, db: AsyncSession = Depends(get_db)):
    now = datetime.datetime.now(ZoneInfo(settings.timezone)).replace(tzinfo=None)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + datetime.timedelta(days=1)
    user_email = _get_current_email(request)
    read_result = await db.execute(select(DailyNewsRead).where(DailyNewsRead.user_email == user_email))
    read_state = read_result.scalar_one_or_none()
    if read_state and read_state.dismissed_date == day_start.date():
        return {"date": day_start.date().isoformat(), "projects": [], "dismissed": True}


    projects_result = await db.execute(select(Project).order_by(Project.sort_order, Project.name))
    final_status_id = (
        select(TaskStatus.id)
        .where(TaskStatus.project_id == Task.project_id)
        .order_by(TaskStatus.sort_order.desc(), TaskStatus.id.desc())
        .limit(1)
        .correlate(Task)
        .scalar_subquery()
    )
    tasks_result = await db.execute(
        select(Task)
        .where(
            Task.is_closed.is_(False),
            Task.status_id != final_status_id,
            Task.due_date.is_not(None),
            or_(Task.start_date.is_(None), Task.start_date <= now),
        )
        .order_by(Task.due_date.asc())
    )
    notes_result = await db.execute(
        select(Affair)
        .where(
            Affair.project_id.is_not(None),
            Affair.is_completed.is_(False),
            Affair.show_in_news.is_(True),
            or_(Affair.is_shared.is_(True), Affair.owner_email == user_email),
            Affair.updated_at >= day_start,
            Affair.updated_at < day_end,
        )
        .order_by(Affair.updated_at.desc())
    )
    comments_result = await db.execute(
        select(ProjectComment)
        .where(ProjectComment.created_at >= day_start, ProjectComment.created_at < day_end)
        .order_by(ProjectComment.created_at.desc())
    )
    events_result = await db.execute(
        select(CalendarEvent)
        .where(
            CalendarEvent.project_id.is_not(None),
            CalendarEvent.start_date < day_end,
            or_(
                CalendarEvent.end_date >= day_start,
                and_(CalendarEvent.end_date.is_(None), CalendarEvent.start_date >= day_start),
            ),
        )
        .order_by(CalendarEvent.start_date.asc())
    )

    projects = projects_result.scalars().all()
    items_by_project: dict[int, list[dict]] = {project.id: [] for project in projects}

    for task in tasks_result.scalars().all():
        items_by_project.setdefault(task.project_id, []).append({
            "type": "task",
            "title": task.title,
            "description": task.description,
            "date": task.due_date.isoformat(),
            "is_overdue": task.due_date < now,
            "url": f"/projects/{task.project_id}/kanban?task={task.id}",
        })
    for event in events_result.scalars().all():
        items_by_project.setdefault(event.project_id, []).append({
            "type": "event",
            "title": event.title,
            "description": event.description,
            "date": event.start_date.isoformat(),
            "is_overdue": False,
            "url": f"/projects/{event.project_id}",
        })
    for note in notes_result.scalars().all():
        items_by_project.setdefault(note.project_id, []).append({
            "type": "note",
            "title": note.title,
            "description": note.description,
            "date": note.updated_at.isoformat(),
            "is_overdue": False,
            "url": f"/affairs?project={note.project_id}&note={note.id}",
        })
    for comment in comments_result.scalars().all():
        items_by_project.setdefault(comment.project_id, []).append({
            "type": "comment",
            "title": comment.content,
            "description": None,
            "date": comment.created_at.isoformat(),
            "is_overdue": False,
            "url": f"/projects/{comment.project_id}",
        })

    result = []
    for project in projects:
        items = items_by_project.get(project.id, [])
        if not items:
            continue
        items.sort(key=lambda item: item["date"])
        result.append({
            "id": project.id,
            "name": project.name,
            "sort_date": items[0]["date"],
            "items": items,
        })
    result.sort(key=lambda project: project["sort_date"])
    return {"date": day_start.date().isoformat(), "projects": result}


@router.post("/daily/dismiss")
async def dismiss_daily_news(request: Request, db: AsyncSession = Depends(get_db)):
    user_email = _get_current_email(request)
    dismissed_date = datetime.datetime.now(ZoneInfo(settings.timezone)).date()
    result = await db.execute(select(DailyNewsRead).where(DailyNewsRead.user_email == user_email))
    read_state = result.scalar_one_or_none()
    if read_state:
        read_state.dismissed_date = dismissed_date
        read_state.updated_at = datetime.datetime.utcnow()
    else:
        db.add(DailyNewsRead(user_email=user_email, dismissed_date=dismissed_date))
    await db.commit()
    return {"dismissed_date": dismissed_date.isoformat()}


@router.get("")
async def list_affairs(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Affair)
        .where(
            Affair.owner_email == _get_current_email(request),
            Affair.is_shared.is_(False),
        )
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
        is_shared=data.is_shared if data.is_shared is not None else not settings.personal_notes_enabled,
        show_in_news=data.show_in_news,
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
            or_(Affair.is_shared.is_(True), Affair.owner_email == _get_current_email(request)),
        )
    )
    affair = result.scalar_one_or_none()
    if not affair:
        raise HTTPException(status_code=404, detail="Заметка не найдена")
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
            or_(Affair.is_shared.is_(True), Affair.owner_email == _get_current_email(request)),
        )
    )
    affair = result.scalar_one_or_none()
    if not affair:
        raise HTTPException(status_code=404, detail="Заметка не найдена")
    await db.delete(affair)
    await db.commit()
    return None
