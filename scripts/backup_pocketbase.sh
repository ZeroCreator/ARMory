#!/bin/bash
# Backup PocketBase data dir (data/pb_data) to data/backups.
# Usage: ./scripts/backup_pocketbase.sh [output_dir]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PB_DATA_DIR="$PROJECT_DIR/data/pb_data"
PB_MIGRATIONS_DIR="$PROJECT_DIR/data/pb_migrations"
BACKUP_DIR="${1:-$PROJECT_DIR/data/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="pocketbase_${TIMESTAMP}.tar.gz"

if [ ! -d "$PB_DATA_DIR" ]; then
    echo "PocketBase data dir not found: $PB_DATA_DIR"
    exit 1
fi

mkdir -p "$BACKUP_DIR"

echo "Creating PocketBase backup: ${BACKUP_FILE}"
tar czf "$BACKUP_DIR/$BACKUP_FILE" -C "$PROJECT_DIR/data" pb_data pb_migrations

echo "Backup saved to: $BACKUP_DIR/$BACKUP_FILE"
