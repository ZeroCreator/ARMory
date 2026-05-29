#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"${SCRIPT_DIR}/run_remote.sh" 'docker compose exec -i beat uv run celery -A conf.celery_app call parser.send-daily-report --queue flat-parser'
