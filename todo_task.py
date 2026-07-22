#!/usr/bin/env python3
"""Отправка сохранённого списка задач в Telegram.

Настройка списка сохраняется через UI (кнопка «Сохранить для Telegram»
в модале «Сохранить список задач») в файл data/telegram_task_list.json.
Запускается планировщиком задач через sh-скрипт scripts/scripts/ARMory/send_todo_tasks.sh.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm import selectinload

# Загружаем .env до импорта app-модулей, чтобы настройки подхватились.
load_dotenv()

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models import Assignee, Project, Task, TaskStatus
from app.telegram import send_telegram_message

logger = logging.getLogger(__name__)

CONFIG_PATH = Path("data/telegram_task_list.json")
TIMEZONE = "Europe/Moscow"

SAVE_LIST_COLUMNS = [
    {"key": "id", "label": "#"},
    {"key": "project_name", "label": "Проект"},
    {"key": "title", "label": "Название"},
    {"key": "description", "label": "Описание"},
    {"key": "status_name", "label": "Статус"},
    {"key": "priority", "label": "Приоритет"},
    {"key": "assignee_name", "label": "Ответственный"},
    {"key": "due_date", "label": "Дедлайн"},
    {"key": "tags", "label": "Теги"},
    {"key": "list_name", "label": "Список"},
    {"key": "created_at", "label": "Создано"},
    {"key": "is_closed", "label": "Закрыто"},
]


def _moscow_str(dt: datetime | None) -> str:
    if not dt:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=dt_timezone.utc)
    return dt.astimezone(ZoneInfo(TIMEZONE)).strftime("%d.%m.%Y %H:%M")


def _priority_label(value: str | None) -> str:
    return {"low": "Низкий", "medium": "Средний", "high": "Высокий"}.get(value or "", value or "—")


def _column_value(task: Task, key: str, projects_map: dict, assignees_map: dict) -> str:
    if key == "id":
        return str(task.id)
    if key == "project_name":
        return projects_map.get(task.project_id, f"Проект #{task.project_id}")
    if key == "title":
        return task.title or ""
    if key == "description":
        return task.description or ""
    if key == "status_name":
        return task.status.name if task.status else "—"
    if key == "priority":
        return _priority_label(task.priority)
    if key == "assignee_name":
        return assignees_map.get(task.assignee_email, task.assignee_email or "—")
    if key == "due_date":
        return _moscow_str(task.due_date)
    if key == "tags":
        return task.tags or "—"
    if key == "list_name":
        return task.list_name or "—"
    if key == "created_at":
        return _moscow_str(task.created_at)
    if key == "is_closed":
        return "Да" if task.is_closed else "Нет"
    return ""


def _format_tasks(tasks, columns: list[str], fmt: str, projects_map: dict, assignees_map: dict) -> str:
    selected = [c for c in SAVE_LIST_COLUMNS if c["key"] in columns]
    if not selected:
        selected = [c for c in SAVE_LIST_COLUMNS if c["key"] == "title"]

    if fmt == "numbered":
        lines = []
        for i, task in enumerate(tasks, 1):
            parts = [_column_value(task, c["key"], projects_map, assignees_map) for c in selected]
            lines.append(f"{i}. {' | '.join(parts)}")
        return "\n".join(lines)

    if fmt == "todo":
        lines = []
        for task in tasks:
            title = _column_value(task, "title", projects_map, assignees_map)
            parts = [
                f"{c['label']}: {_column_value(task, c['key'], projects_map, assignees_map)}"
                for c in selected if c["key"] != "title"
            ]
            line = f"{'[x]' if task.is_closed else '[ ]'} {title}"
            if parts:
                line += " (" + ", ".join(parts) + ")"
            lines.append(line)
        return "\n".join(lines)

    if fmt == "markdown":
        headers = [c["label"] for c in selected]
        rows = ["| " + " | ".join(headers) + " |"]
        rows.append("| " + " | ".join(["---"] * len(selected)) + " |")
        for task in tasks:
            cells = [_column_value(task, c["key"], projects_map, assignees_map) for c in selected]
            rows.append("| " + " | ".join(cells) + " |")
        return "\n".join(rows)

    if fmt == "oneline":
        lines = []
        for task in tasks:
            parts = [_column_value(task, c["key"], projects_map, assignees_map) for c in selected]
            lines.append(" | ".join(parts))
        return "\n".join(lines)

    return ""


def _load_config() -> dict | None:
    if not CONFIG_PATH.exists():
        return None
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("Ошибка чтения конфига %s: %s", CONFIG_PATH, e)
        return None


async def _fetch_tasks(config: dict):
    async with AsyncSessionLocal() as db:
        projects_result = await db.execute(select(Project))
        projects_map = {p.id: p.name for p in projects_result.scalars().all()}

        assignees_result = await db.execute(select(Assignee))
        assignees_map = {a.email: a.name for a in assignees_result.scalars().all()}

        query = select(Task).options(selectinload(Task.status))
        filters = config.get("filters", {})

        if not config.get("is_global", False) and config.get("project_id"):
            query = query.where(Task.project_id == int(config["project_id"]))

        if filters.get("project_id"):
            query = query.where(Task.project_id == int(filters["project_id"]))
        if filters.get("status"):
            query = query.where(Task.status.has(TaskStatus.name == filters["status"]))
        if filters.get("priority"):
            query = query.where(Task.priority == filters["priority"])
        if filters.get("assignee"):
            query = query.where(Task.assignee_email == filters["assignee"])
        if filters.get("list_name"):
            query = query.where(Task.list_name == filters["list_name"])
        if filters.get("closed") not in (None, ""):
            query = query.where(Task.is_closed == bool(int(filters["closed"])))
        if filters.get("tags"):
            for tag in filters["tags"].split(","):
                tag = tag.strip().lower()
                if tag:
                    query = query.where(Task.tags.ilike(f"%{tag}%"))
        if filters.get("search"):
            search = f"%{filters['search'].lower()}%"
            query = query.where((Task.title.ilike(search)) | (Task.description.ilike(search)))

        result = await db.execute(
            query.order_by(Task.is_closed.asc(), Task.sort_order.asc(), Task.created_at.asc())
        )
        tasks = result.scalars().all()
        return tasks, projects_map, assignees_map


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    config = _load_config()
    if config is None:
        logger.error("Конфигурация списка не найдена: %s", CONFIG_PATH)
        return

    settings = get_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.error("Telegram не настроен: TELEGRAM_BOT_TOKEN и/или TELEGRAM_CHAT_ID не заданы")
        return

    tasks, projects_map, assignees_map = await _fetch_tasks(config)
    if not tasks:
        logger.info("Нет задач для отправки")
        return

    text = _format_tasks(
        tasks,
        config.get("columns", ["title", "status_name", "priority", "assignee_name", "due_date"]),
        config.get("format", "todo"),
        projects_map,
        assignees_map,
    )

    caption = config.get("caption", "📋 <b>Список задач</b>")
    full_text = f"{caption}\n\n{text}"
    if len(full_text) > 4000:
        full_text = full_text[:3990] + "\n…"

    success, error = await send_telegram_message(full_text)
    if not success:
        logger.error("Не удалось отправить список в Telegram: %s", error)
        raise SystemExit(1)
    logger.info("Список задач отправлен в Telegram (%d задач)", len(tasks))


if __name__ == "__main__":
    asyncio.run(main())
