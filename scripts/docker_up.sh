#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"${SCRIPT_DIR}/run_remote.sh" 'docker compose up -d trendagent-worker watch-trendagent-token-updates'
