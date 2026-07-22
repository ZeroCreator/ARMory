"""Общая логика MCP для ARMory.

Используется как stdio MCP-сервером, так и HTTP endpoint'ом.
"""

import json
import os
from typing import Any

import httpx

ARMORY_BASE_URL = os.environ.get("ARMORY_BASE_URL", "http://localhost:8067").rstrip("/")

TOOLS = [
    {
        "name": "get_task",
        "description": "Получить задачу канбана по task_id. project_id можно не указывать — номера задач сквозные.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": ["integer", "null"]},
                "task_id": {"type": "integer"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "list_tasks",
        "description": "Получить список задач проекта",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "integer"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "create_task",
        "description": "Создать новую задачу в проекте",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "integer"},
                "status_id": {"type": "integer"},
                "title": {"type": "string"},
                "description": {"type": ["string", "null"]},
                "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                "tags": {"type": ["string", "null"]},
                "list_name": {"type": ["string", "null"]},
                "due_date": {"type": ["string", "null"]},
                "assignee_email": {"type": ["string", "null"]},
            },
            "required": ["project_id", "status_id", "title"],
        },
    },
    {
        "name": "update_task",
        "description": "Обновить задачу (статус, название, описание, приоритет, теги и т.д.)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "integer"},
                "task_id": {"type": "integer"},
                "status_id": {"type": ["integer", "null"]},
                "title": {"type": ["string", "null"]},
                "description": {"type": ["string", "null"]},
                "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                "is_closed": {"type": "boolean"},
                "tags": {"type": ["string", "null"]},
                "list_name": {"type": ["string", "null"]},
                "due_date": {"type": ["string", "null"]},
                "assignee_email": {"type": ["string", "null"]},
            },
            "required": ["project_id", "task_id"],
        },
    },
]


def _base_url(override: str | None = None) -> str:
    return (override or ARMORY_BASE_URL).rstrip("/")


def _api_request(method: str, path: str, json_body: dict[str, Any] | None = None, base_url: str | None = None) -> dict[str, Any]:
    url = f"{_base_url(base_url)}{path}"
    with httpx.Client(timeout=30.0) as client:
        try:
            response = client.request(method, url, json=json_body)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            return {"error": f"HTTP {exc.response.status_code}: {exc.response.text}"}
        except Exception as exc:
            return {"error": str(exc)}


def handle_initialize(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocolVersion": params.get("protocolVersion", "2024-11-05"),
        "capabilities": {"tools": {}},
        "serverInfo": {"name": "armory-mcp", "version": "0.1.0"},
    }


def handle_tools_list() -> dict[str, Any]:
    return {"tools": TOOLS}


def handle_tool_call(params: dict[str, Any], base_url: str | None = None) -> dict[str, Any]:
    name = params.get("name")
    arguments = params.get("arguments", {})
    result: dict[str, Any]

    if name == "get_task":
        project_id = arguments.get("project_id")
        task_id = arguments["task_id"]
        if project_id:
            result = _api_request("GET", f"/api/projects/{project_id}/tasks/{task_id}", base_url=base_url)
        else:
            result = _api_request("GET", f"/api/tasks/{task_id}", base_url=base_url)
    elif name == "list_tasks":
        project_id = arguments["project_id"]
        result = _api_request("GET", f"/api/projects/{project_id}/tasks", base_url=base_url)
    elif name == "create_task":
        project_id = arguments["project_id"]
        result = _api_request("POST", f"/api/projects/{project_id}/tasks", arguments, base_url=base_url)
    elif name == "update_task":
        project_id = arguments["project_id"]
        task_id = arguments["task_id"]
        payload = {k: v for k, v in arguments.items() if k not in ("project_id", "task_id") and v is not None}
        result = _api_request("PATCH", f"/api/projects/{project_id}/tasks/{task_id}", payload, base_url=base_url)
    else:
        return {"error": f"Unknown tool: {name}"}

    return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]}


def handle_message(msg: dict[str, Any], base_url: str | None = None) -> dict[str, Any] | None:
    method = msg.get("method")
    params = msg.get("params", {})

    if method == "initialize":
        return handle_initialize(params)
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return handle_tools_list()
    if method == "tools/call":
        return handle_tool_call(params, base_url=base_url)

    return {"error": f"Method not found: {method}"}
