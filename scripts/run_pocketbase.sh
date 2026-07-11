#!/bin/bash
# Run PocketBase locally without Docker.
# Expected binary path: ./pocketbase/pocketbase
# Data dir: ./data/pb_data
# Migrations dir: ./data/pb_migrations

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
POCKETBASE_DIR="$PROJECT_DIR/pocketbase"
POCKETBASE_BIN="$POCKETBASE_DIR/pocketbase"
PB_DATA_DIR="$PROJECT_DIR/data/pb_data"
PB_MIGRATIONS_DIR="$PROJECT_DIR/data/pb_migrations"

# Load .env if present
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    # shellcheck source=/dev/null
    . "$PROJECT_DIR/.env"
    set +a
fi

POCKETBASE_ADMIN_EMAIL="${POCKETBASE_ADMIN_EMAIL:-admin@example.com}"
POCKETBASE_ADMIN_PASSWORD="${POCKETBASE_ADMIN_PASSWORD:-changeme}"
POCKETBASE_HTTP="${POCKETBASE_HTTP:-127.0.0.1:8090}"

if [ ! -x "$POCKETBASE_BIN" ]; then
    echo "PocketBase binary not found: $POCKETBASE_BIN"
    echo "Download and unpack it first, for example:"
    echo "  unzip ~/downloads/pocketbase_0.39.6_linux_amd64.zip -d $POCKETBASE_DIR"
    exit 1
fi

mkdir -p "$PB_DATA_DIR" "$PB_MIGRATIONS_DIR"

# Create or update admin user before starting the server.
"$POCKETBASE_BIN" superuser upsert "$POCKETBASE_ADMIN_EMAIL" "$POCKETBASE_ADMIN_PASSWORD" --dir="$PB_DATA_DIR" --migrationsDir="$PB_MIGRATIONS_DIR"

echo "Starting PocketBase on http://$POCKETBASE_HTTP"
exec "$POCKETBASE_BIN" serve --http="$POCKETBASE_HTTP" --dir="$PB_DATA_DIR" --migrationsDir="$PB_MIGRATIONS_DIR"
