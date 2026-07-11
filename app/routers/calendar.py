import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import CalendarEvent
from app.telegram import send_telegram_message
from app.config import get_settings

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


class EventCreate(BaseModel):
    title: str
    description: str | None = None
    note: str | None = None
    start_date: str
    end_date: str | None = None
    all_day: bool = False
    color: str | None = None
    reminder_minutes: int | None = None


class EventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    note: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    all_day: bool | None = None
    color: str | None = None
    reminder_minutes: int | None = None


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
            "reminder_minutes": e.reminder_minutes,
            "notified_at": e.notified_at.isoformat() if e.notified_at else None,
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
        reminder_minutes=data.reminder_minutes,
        notified_at=None,
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

    reset_notification = False
    if data.title is not None:
        event.title = data.title
    if data.description is not None:
        event.description = data.description
    if data.note is not None:
        event.note = data.note
    if data.start_date is not None:
        event.start_date = _parse_iso(data.start_date)
        reset_notification = True
    if data.end_date is not None:
        event.end_date = _parse_iso(data.end_date)
    if data.all_day is not None:
        event.all_day = data.all_day
    if data.color is not None:
        event.color = data.color
    if "reminder_minutes" in data.model_fields_set:
        event.reminder_minutes = data.reminder_minutes
        reset_notification = True

    if reset_notification:
        event.notified_at = None

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


@router.get("/telegram-config")
async def telegram_config():
    """Проверить, что Telegram-настройки прочитаны приложением."""
    settings = get_settings()
    return {
        "reminder_enabled": settings.telegram_reminder_enabled,
        "bot_token_configured": bool(settings.telegram_bot_token),
        "chat_id": settings.telegram_chat_id,
    }


@router.post("/test-telegram-reminder")
async def test_telegram_reminder():
    """Отправить тестовое сообщение в Telegram для проверки настроек."""
    text = "<b>🔔 Тестовое напоминание</b>\n\nЕсли вы видите это сообщение, Telegram-уведомления настроены правильно."
    success, error = await send_telegram_message(text)
    if success:
        return {"message": "Тестовое сообщение отправлено"}
    raise HTTPException(
        status_code=500,
        detail={
            "error": "Не удалось отправить сообщение в Telegram",
            "telegram_response": error,
        },
    )


@router.get("/active-reminders")
async def active_reminders(db: AsyncSession = Depends(get_db)):
    """Вернуть события, время напоминания о которых уже наступило.

    Независимо от отправки в Telegram — показываем в приложении, как только
    наступил момент start_date - reminder_minutes. Событие продолжает
    отображаться после начала (в режиме просрочки), пока пользователь
    не закроет его вручную.
    """
    settings = get_settings()
    now = datetime.datetime.now(ZoneInfo(settings.timezone)).replace(tzinfo=None)
    result = await db.execute(
        select(CalendarEvent)
        .where(CalendarEvent.reminder_minutes.isnot(None))
        .order_by(CalendarEvent.start_date)
    )
    events = result.scalars().all()
    active = []
    for event in events:
        reminder_moment = event.start_date - datetime.timedelta(minutes=event.reminder_minutes)
        if now >= reminder_moment:
            active.append(event)
    return [
        {
            "id": e.id,
            "title": e.title,
            "description": e.description,
            "start_date": e.start_date.isoformat() if e.start_date else None,
            "end_date": e.end_date.isoformat() if e.end_date else None,
            "all_day": e.all_day,
            "color": e.color,
            "reminder_minutes": e.reminder_minutes,
        }
        for e in active
    ]
