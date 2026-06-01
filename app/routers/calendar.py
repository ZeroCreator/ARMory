import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import CalendarEvent

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


class EventCreate(BaseModel):
    title: str
    description: str | None = None
    note: str | None = None
    start_date: str
    end_date: str | None = None
    all_day: bool = False
    color: str | None = None


class EventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    note: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    all_day: bool | None = None
    color: str | None = None


def _parse_iso(dt_str: str | None) -> datetime.datetime | None:
    if not dt_str:
        return None
    try:
        return datetime.datetime.fromisoformat(dt_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid datetime format: {dt_str}")


@router.get("/events")
async def list_events(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CalendarEvent).order_by(desc(CalendarEvent.start_date)))
    events = result.scalars().all()
    return [
        {
            "id": e.id,
            "title": e.title,
            "description": e.description,
            "note": e.note,
            "start_date": e.start_date.isoformat() if e.start_date else None,
            "end_date": e.end_date.isoformat() if e.end_date else None,
            "all_day": e.all_day,
            "color": e.color,
        }
        for e in events
    ]


@router.post("/events")
async def create_event(data: EventCreate, db: AsyncSession = Depends(get_db)):
    start = _parse_iso(data.start_date)
    if not start:
        raise HTTPException(status_code=400, detail="start_date is required")
    end = _parse_iso(data.end_date)
    event = CalendarEvent(
        title=data.title,
        description=data.description,
        note=data.note,
        start_date=start,
        end_date=end,
        all_day=data.all_day,
        color=data.color or "#a78bfa",
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return {"id": event.id, "message": "Событие создано"}


@router.patch("/events/{event_id}")
async def update_event(event_id: int, data: EventUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CalendarEvent).where(CalendarEvent.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Событие не найдено")

    if data.title is not None:
        event.title = data.title
    if data.description is not None:
        event.description = data.description
    if data.note is not None:
        event.note = data.note
    if data.start_date is not None:
        event.start_date = _parse_iso(data.start_date)
    if data.end_date is not None:
        event.end_date = _parse_iso(data.end_date)
    if data.all_day is not None:
        event.all_day = data.all_day
    if data.color is not None:
        event.color = data.color

    await db.commit()
    await db.refresh(event)
    return {"id": event.id, "message": "Событие обновлено"}


@router.delete("/events/{event_id}")
async def delete_event(event_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CalendarEvent).where(CalendarEvent.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Событие не найдено")
    await db.delete(event)
    await db.commit()
    return {"message": "Событие удалено"}
