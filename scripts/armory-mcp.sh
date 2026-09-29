#!/bin/bash
# stdio MCP-сервер для интеграции AI-ассистентов с kanban ARMory.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ARMORY_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${ARMORY_ROOT}" || exit 1
exec "${ARMORY_ROOT}/.venv/bin/python" -m app.agent_integration.armory_mcp
