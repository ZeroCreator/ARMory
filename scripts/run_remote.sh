#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../.env"

if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

REMOTE_DIR="${FLAT_PARSER_DIR:-/home/devel/flat-parser}"
REMOTE_CMD="${1:-}"

if [ -z "$REMOTE_CMD" ]; then
    echo "Usage: $0 '<command>'" >&2
    exit 1
fi

cd "$REMOTE_DIR" && eval "$REMOTE_CMD"
