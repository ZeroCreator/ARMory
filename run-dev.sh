#!/bin/bash
set -e

cd "$(dirname "$0")"

PORT="${PORT:-8067}"

echo "Starting ARMory on http://127.0.0.1:$PORT"
exec uv run uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --reload
