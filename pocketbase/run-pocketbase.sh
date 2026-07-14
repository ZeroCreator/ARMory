#!/bin/sh
# Local helper to start PocketBase with an auto-created/updated superuser.
# Credentials are read from environment variables or fall back to defaults.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="${SCRIPT_DIR}/../data/pb_data"

POCKETBASE_ADMIN_EMAIL="${POCKETBASE_ADMIN_EMAIL:-admin@example.com}"
POCKETBASE_ADMIN_PASSWORD="${POCKETBASE_ADMIN_PASSWORD:-changeme}"

"${SCRIPT_DIR}/pocketbase" superuser upsert "${POCKETBASE_ADMIN_EMAIL}" "${POCKETBASE_ADMIN_PASSWORD}" --dir="${DATA_DIR}"
"${SCRIPT_DIR}/pocketbase" serve --http=127.0.0.1:8090 --dir="${DATA_DIR}"
