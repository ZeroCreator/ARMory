#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"${SCRIPT_DIR}/run_remote.sh" 'docker rm -f flat-parser-trendagent-worker-1 flat-parser-watch-trendagent-token-updates-1'
