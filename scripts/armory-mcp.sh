#!/bin/bash
# stdio MCP-сервер для интеграции AI-ассистентов с kanban ARMory.
cd /home/zerocreator/ARMory || exit 1
exec .venv/bin/python mcp/armory_mcp.py
