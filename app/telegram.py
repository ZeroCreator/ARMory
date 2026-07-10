import datetime
import logging
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import CalendarEvent

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def _now_in_timezone(tz_name: str) -> datetime.datetime:
    return datetime.datetime.now(ZoneInfo(tz_name))


def _format_event_time(event: CalendarEvent, tz_name: str) -> str:
    if event.all_day:
        return event.start_date.strftime("%d.%m.%Y") + " (весь день)"
    tz = ZoneInfo(tz_name)
    start_local = event.start_date
    if start_local.tzinfo is None:
        start_local = start_local.replace(tzinfo=tz)
    else:
        start_local = start_local.astimezone(tz)
    return start_local.strftime("%d.%m.%Y %H:%M")


async def send_telegram_message(text: str) -> tuple[bool, str | None]:
    settings = get_settings()
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
    if not token:
        return False, "TELEGRAM_BOT_TOKEN не задан"
    if not chat_id:
        return False, "TELEGRAM_CHAT_ID не задан"

    url = TELEGRAM_API_URL.format(token=token)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            if data.get("ok"):
                return True, None
            error_text = response.text
            logger.error("Telegram вернул ok=false: %s", error_text)
            return False, error_text
    except httpx.HTTPStatusError as e:
        error_text = e.response.text
        logger.error("Ошибка отправки Telegram-уведомления: %s", error_text)
        return False, error_text
    except httpx.HTTPError as e:
        logger.error("Ошибка отправки Telegram-уведомления: %s", e)
        return False, str(e)


async def check_and_send_calendar_reminders(db: AsyncSession) -> None:
    settings = get_settings()
    if not settings.telegram_reminder_enabled:
        logger.debug("Telegram-напоминания отключены в настройках")
        return
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.warning(
            "Telegram-напоминания включены, но не настроены: token=%s chat_id=%s",
            bool(settings.telegram_bot_token),
            bool(settings.telegram_chat_id),
        )
        return

    now = _now_in_timezone(settings.timezone)
    now_naive = now.replace(tzinfo=None)
    logger.debug("Проверка напоминаний календаря на %s", now)

    result = await db.execute(
        select(CalendarEvent).where(
            CalendarEvent.reminder_minutes.isnot(None),
            CalendarEvent.notified_at.is_(None),
        )
    )
    events = result.scalars().all()
    logger.debug("Найдено событий для проверки: %d", len(events))

    for event in events:
        if not event.start_date:
            logger.debug("Событие %d пропущено: отсутствует start_date", event.id)
            continue
        reminder_moment = event.start_date - datetime.timedelta(minutes=event.reminder_minutes)
        logger.debug(
            "Событие %d: start=%s reminder_minutes=%s reminder_moment=%s now=%s",
            event.id,
            event.start_date,
            event.reminder_minutes,
            reminder_moment,
            now_naive,
        )
        if now_naive >= reminder_moment:
            reminder_time = now_naive.strftime("%d.%m.%Y %H:%M")
            text = (
                f"<b>🔔 Напоминание о событии</b>\n"
                f"<i>Отправлено: {reminder_time}</i>\n"
            )
            if event.reminder_minutes:
                text += f"<i>За {event.reminder_minutes} минут до начала</i>\n"
            text += (
                f"\n"
                f"<b>{event.title}</b>\n"
                f"🕐 Начало: {_format_event_time(event, settings.timezone)}\n"
            )
            if event.description:
                text += f"📝 {event.description}\n"
            if event.note:
                text += f"📌 {event.note}\n"

            logger.info("Отправка напоминания для события %d", event.id)
            success, _ = await send_telegram_message(text)
            if success:
                event.notified_at = now_naive
                await db.commit()
                logger.info("Напоминание для события %d отправлено", event.id)
