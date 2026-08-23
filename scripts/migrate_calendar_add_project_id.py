#!/usr/bin/env python3
"""Добавить колонку project_id в таблицу calendar_events."""
import asyncio
import aiosqlite
import os
import sys


def get_db_path() -> str:
    # Берём путь из переменной окружения DATABASE_URL, иначе используем умолчание.
    url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./armory.db")
    if url.startswith("sqlite+aiosqlite:///"):
        return url[len("sqlite+aiosqlite:///"):]
    if url.startswith("sqlite:///"):
        return url[len("sqlite:////"):]
    raise RuntimeError(f"Unsupported DATABASE_URL: {url}")


async def main():
    db_path = get_db_path()
    print(f"Using database: {db_path}")
    async with aiosqlite.connect(db_path) as db:
        # Проверяем, есть ли уже колонка
        cursor = await db.execute("PRAGMA table_info(calendar_events)")
        columns = {row[1] for row in await cursor.fetchall()}
        if "project_id" in columns:
            print("Column project_id already exists.")
            return
        await db.execute(
            "ALTER TABLE calendar_events ADD COLUMN project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL"
        )
        await db.commit()
        print("Column project_id added successfully.")


if __name__ == "__main__":
    asyncio.run(main())
