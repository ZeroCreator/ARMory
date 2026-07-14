#!/bin/bash
set -e

cd "$(dirname "$0")"

# Local development helper: starts PocketBase in the background, then ARMory.
# PocketBase data lives in ./data/pb_data (same path as Docker compose).

export POCKETBASE_INTERNAL_URL="${POCKETBASE_INTERNAL_URL:-http://127.0.0.1:8090}"
PORT="${PORT:-8067}"

echo "Starting PocketBase..."
./pocketbase/run-pocketbase.sh &
POCKETBASE_PID=$!

# Ensure PocketBase is stopped when the script exits.
cleanup() {
    echo "Stopping PocketBase (pid $POCKETBASE_PID)..."
    kill "$POCKETBASE_PID" 2>/dev/null || true
    wait "$POCKETBASE_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Wait briefly for PocketBase to bind.
sleep 1

echo "Starting ARMory on http://127.0.0.1:$PORT"
exec uv run uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --reload
