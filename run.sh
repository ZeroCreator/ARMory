#!/bin/bash
set -e

cd "$(dirname "$0")"

# uv автоматически создаст .venv и установит зависимости при первом запуске
PORT=${PORT:-8088}
exec uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT --reload
