#!/bin/bash
# Отправка сохранённого списка задач в Telegram.
# Запускается планировщиком задач ARMory.

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT_DIR"

mkdir -p data

if [ -f ".venv/bin/activate" ]; then
    # shellcheck source=/dev/null
    source .venv/bin/activate
    exec python todo_task.py
elif command -v uv >/dev/null 2>&1; then
    exec uv run python todo_task.py
else
    exec python todo_task.py
fi
