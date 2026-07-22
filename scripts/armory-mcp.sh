#!/bin/bash
# MCP-сервер для интеграции Kimi Code CLI с канбаном ARMory.
cd /home/zerocreator/ARMory || exit 1
exec .venv/bin/python mcp/armory_mcp.py
