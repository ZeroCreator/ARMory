#!/usr/bin/env python3
"""MCP-сервер для интеграции Kimi Code CLI с канбаном ARMory.

Читает из stdin, пишет в stdout. Делает HTTP-запросы к API ARMory.
Базовый URL API задаётся переменной окружения ARMORY_BASE_URL
(по умолчанию http://localhost:8067).
"""

import json
import os
import sys
from typing import Any

import httpx

ARMORY_BASE_URL = os.environ.get("ARMORY_BASE_URL", "http://localhost:8067").rstrip("/")


def send_message(msg: dict[str, Any]) -> None:
    data = json.dumps(msg, ensure_ascii=False)
    sys.stdout.write(f"Content-Length: {len(data.encode('utf-8'))}\r\n\r\n{data}")
    sys.stdout.flush()


def make_error(id_: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": id_,
        "error": {"code": code, "message": message},
    }


def handle_initialize(id_: Any, params: dict[str, Any]) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": id_,
        "result": {
            "protocolVersion": params.get("protocolVersion", "2024-11-05"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "armory-mcp", "version": "0.1.0"},
        },
    }


def handle_tools_list(id_: Any) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": id_,
        "result": {
            "tools": [
                {
                    "name": "get_task",
                    "description": "Получить задачу канбана по project_id и task_id",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "project_id": {"type": "integer"},
                            "task_id": {"type": "integer"},
                        },
                        "required": ["project_id", "task_id"],
                    },
                },
                {
                    "name": "list_tasks",
                    "description": "Получить список задач проекта",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "project_id": {"type": "integer"},
                        },
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
        },
    }


def _api_request(method: str, path: str, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{ARMORY_BASE_URL}{path}"
    with httpx.Client(timeout=30.0) as client:
        try:
            response = client.request(method, url, json=json_body)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            return {"error": f"HTTP {exc.response.status_code}: {exc.response.text}"}
        except Exception as exc:
            return {"error": str(exc)}


def handle_tool_call(id_: Any, params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    arguments = params.get("arguments", {})
    result: dict[str, Any]

    if name == "get_task":
        project_id = arguments["project_id"]
        task_id = arguments["task_id"]
        result = _api_request("GET", f"/api/projects/{project_id}/tasks/{task_id}")
    elif name == "list_tasks":
        project_id = arguments["project_id"]
        result = _api_request("GET", f"/api/projects/{project_id}/tasks")
    elif name == "create_task":
        project_id = arguments["project_id"]
        result = _api_request("POST", f"/api/projects/{project_id}/tasks", arguments)
    elif name == "update_task":
        project_id = arguments["project_id"]
        task_id = arguments["task_id"]
        payload = {k: v for k, v in arguments.items() if k not in ("project_id", "task_id") and v is not None}
        result = _api_request("PATCH", f"/api/projects/{project_id}/tasks/{task_id}", payload)
    else:
        return make_error(id_, -32601, f"Unknown tool: {name}")

    return {
        "jsonrpc": "2.0",
        "id": id_,
        "result": {
            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]
        },
    }


def handle_message(msg: dict[str, Any]) -> dict[str, Any] | None:
    method = msg.get("method")
    id_ = msg.get("id")
    params = msg.get("params", {})

    if method == "initialize":
        return handle_initialize(id_, params)
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return handle_tools_list(id_)
    if method == "tools/call":
        return handle_tool_call(id_, params)

    if id_ is not None:
        return make_error(id_, -32601, f"Method not found: {method}")
    return None


def main() -> None:
    while True:
        headers = {}
        while True:
            line = sys.stdin.readline()
            if not line:
                return
            line = line.strip()
            if line == "":
                break
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()

        length = int(headers.get("content-length", "0"))
        if length == 0:
            continue

        raw = sys.stdin.read(length)
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            send_message(make_error(None, -32700, "Parse error"))
            continue

        response = handle_message(msg)
        if response is not None:
            send_message(response)


if __name__ == "__main__":
    main()
