"""MCP-инструменты для создания и управления задачами в канбане ARMory."""

from __future__ import annotations

import asyncio
from functools import wraps
from typing import Any, Literal

import httpx
from mcp.server.fastmcp import FastMCP

from app.config import get_settings


def _base_url(override: str | None = None) -> str:
    settings = get_settings()
    url = override or settings.armory_base_url
    if not url:
        raise RuntimeError("ARMORY_BASE_URL is not configured")
    return url.rstrip("/")


def _api_request(
    method: str,
    path: str,
    json_body: dict[str, Any] | None = None,
    base_url: str | None = None,
) -> Any:
    """Выполняет запрос к REST API ARMory с помощью сервисного ключа MCP."""
    settings = get_settings()
    headers: dict[str, str] = {}
    if settings.mcp_api_key:
        headers["Authorization"] = f"Bearer {settings.mcp_api_key}"

    try:
        with httpx.Client(timeout=30.0, trust_env=False) as client:
            response = client.request(
                method,
                f"{_base_url(base_url)}{path}",
                json=json_body,
                headers=headers,
            )
        response.raise_for_status()
        if response.status_code == 204:
            return None
        return response.json()
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json()
        except ValueError:
            detail = exc.response.text
        return {"error": f"HTTP {exc.response.status_code}", "detail": detail}
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        return {"error": str(exc)}


def _error(result: Any) -> bool:
    return isinstance(result, dict) and "error" in result


def _list_projects(query: str | None = None) -> list[dict[str, Any]] | dict[str, Any]:
    projects = _api_request("GET", "/api/projects")
    if _error(projects):
        return projects
    needle = (query or "").strip().casefold()
    items = [
        {"id": item["id"], "name": item["name"]}
        for item in projects
        if not needle or needle in item.get("name", "").casefold()
    ]
    return items


def _resolve_project(
    project_id: int | None = None,
    project_name: str | None = None,
) -> dict[str, Any]:
    projects = _api_request("GET", "/api/projects")
    if _error(projects):
        return projects

    if project_id is not None:
        matches = [project for project in projects if project.get("id") == project_id]
        if matches:
            return matches[0]
        return {"error": f"ARMory project {project_id} was not found"}

    query = (project_name or "").strip().casefold()
    if not query:
        return {
            "error": "Specify project_id or project_name",
            "available_projects": [
                {"id": project["id"], "name": project["name"]}
                for project in projects
            ],
        }

    exact = [project for project in projects if project.get("name", "").casefold() == query]
    matches = exact or [
        project for project in projects if query in project.get("name", "").casefold()
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        return {"error": f"No ARMory project matches '{project_name}'"}
    return {
        "error": f"Project name '{project_name}' is ambiguous; choose a project_id",
        "matches": [{"id": item["id"], "name": item["name"]} for item in matches],
    }


def _project_statuses(project_id: int) -> list[dict[str, Any]] | dict[str, Any]:
    statuses = _api_request("GET", f"/api/projects/{project_id}/task-statuses")
    if _error(statuses):
        return statuses
    return sorted(statuses, key=lambda status: (status.get("sort_order", 0), status.get("id", 0)))


def _resolve_status(
    statuses: list[dict[str, Any]],
    status_id: int | None = None,
    status_name: str | None = None,
) -> dict[str, Any] | None:
    if status_id is not None:
        return next((status for status in statuses if status.get("id") == status_id), None)
    if status_name:
        query = status_name.strip().casefold()
        return next((status for status in statuses if status.get("name", "").casefold() == query), None)
    return statuses[0] if statuses else None


def _task_link(project_id: int, task_id: int) -> str:
    public_url = get_settings().armory_public_url.rstrip("/")
    return f"{public_url}/projects/{project_id}/kanban?task={task_id}"


def _with_task_link(task: dict[str, Any]) -> dict[str, Any]:
    result = dict(task)
    task_id = result.get("id")
    project_id = result.get("project_id")
    if task_id is not None:
        result["task_id"] = task_id
    if task_id is not None and project_id is not None:
        result["url"] = _task_link(project_id, task_id)
    return result


def _register_blocking_tool(server: FastMCP):
    """Регистрирует синхронный обработчик без блокировки цикла событий MCP."""
    def register(function):
        @wraps(function)
        async def run_in_thread(*args, **kwargs):
            return await asyncio.to_thread(function, *args, **kwargs)

        server.tool()(run_in_thread)
        return function

    return register


def register_tools(server: FastMCP) -> None:
    @_register_blocking_tool(server)
    def list_projects(query: str | None = None) -> dict[str, Any]:
        """Возвращает проекты ARMory с фильтром по части названия, если он задан."""
        projects = _list_projects(query)
        if _error(projects):
            return projects
        return {"projects": projects, "count": len(projects)}

    @_register_blocking_tool(server)
    def list_task_statuses(
        project_id: int | None = None,
        project_name: str | None = None,
    ) -> dict[str, Any]:
        """Возвращает колонки канбана проекта ARMory."""
        project = _resolve_project(project_id, project_name)
        if _error(project):
            return project
        statuses = _project_statuses(project["id"])
        if _error(statuses):
            return statuses
        return {
            "project": {"id": project["id"], "name": project["name"]},
            "statuses": statuses,
        }

    @_register_blocking_tool(server)
    def list_tasks(
        project_id: int | None = None,
        project_name: str | None = None,
    ) -> dict[str, Any]:
        """Возвращает задачи проекта ARMory. Если проект неясен, сначала вызовите list_projects."""
        project = _resolve_project(project_id, project_name)
        if _error(project):
            return project
        tasks = _api_request("GET", f"/api/projects/{project['id']}/tasks")
        if _error(tasks):
            return tasks
        return {
            "project": {"id": project["id"], "name": project["name"]},
            "tasks": [_with_task_link(task) for task in tasks],
            "count": len(tasks),
        }

    @_register_blocking_tool(server)
    def create_task(
        title: str,
        project_name: str | None = None,
        project_id: int | None = None,
        description: str | None = None,
        status_name: str | None = None,
        status_id: int | None = None,
        priority: Literal["low", "medium", "high"] = "medium",
        tags: str | None = None,
        list_name: str | None = None,
        due_date: str | None = None,
        assignee_email: str | None = None,
    ) -> dict[str, Any]:
        """Создаёт задачу ARMory и возвращает её глобальный номер и ссылку на канбан."""
        project = _resolve_project(project_id, project_name)
        if _error(project):
            return project
        statuses = _project_statuses(project["id"])
        if _error(statuses):
            return statuses
        status = _resolve_status(statuses, status_id, status_name)
        if status is None:
            return {
                "error": "The requested status was not found or this project has no statuses",
                "available_statuses": [
                    {"id": item["id"], "name": item["name"]} for item in statuses
                ],
            }

        payload: dict[str, Any] = {
            "title": title,
            "status_id": status["id"],
            "priority": priority,
        }
        for key, value in {
            "description": description,
            "tags": tags,
            "list_name": list_name,
            "due_date": due_date,
            "assignee_email": assignee_email,
        }.items():
            if value is not None:
                payload[key] = value

        task = _api_request("POST", f"/api/projects/{project['id']}/tasks", payload)
        if _error(task):
            return task
        result = _with_task_link(task)
        result["project_name"] = project["name"]
        result["status_name"] = status["name"]
        return result

    @_register_blocking_tool(server)
    def get_task(task_id: int) -> dict[str, Any]:
        """Возвращает задачу по её глобальному номеру в ARMory."""
        task = _api_request("GET", f"/api/tasks/{task_id}")
        return _with_task_link(task) if not _error(task) else task

    @_register_blocking_tool(server)
    def update_task(
        task_id: int,
        project_id: int | None = None,
        status_name: str | None = None,
        status_id: int | None = None,
        title: str | None = None,
        description: str | None = None,
        priority: Literal["low", "medium", "high"] | None = None,
        is_closed: bool | None = None,
        tags: str | None = None,
        list_name: str | None = None,
        due_date: str | None = None,
        assignee_email: str | None = None,
        result: str | None = None,
    ) -> dict[str, Any]:
        """Изменяет указанные поля задачи. Пропущенные поля остаются без изменений."""
        task: dict[str, Any] | None = None
        if project_id is None or status_name is not None:
            task = _api_request("GET", f"/api/tasks/{task_id}")
            if _error(task):
                return task
            project_id = project_id or task.get("project_id")
        if project_id is None:
            return {"error": "Could not resolve the task's project_id"}

        payload: dict[str, Any] = {}
        for key, value in {
            "status_id": status_id,
            "title": title,
            "description": description,
            "priority": priority,
            "is_closed": is_closed,
            "tags": tags,
            "list_name": list_name,
            "due_date": due_date,
            "assignee_email": assignee_email,
            "result": result,
        }.items():
            if value is not None:
                payload[key] = value

        if status_name is not None and status_id is None:
            statuses = _project_statuses(project_id)
            if _error(statuses):
                return statuses
            status = _resolve_status(statuses, status_name=status_name)
            if status is None:
                return {
                    "error": f"Status '{status_name}' was not found",
                    "available_statuses": [
                        {"id": item["id"], "name": item["name"]} for item in statuses
                    ],
                }
            payload["status_id"] = status["id"]

        if not payload:
            return {"error": "No task fields were provided to update"}

        updated = _api_request(
            "PATCH",
            f"/api/projects/{project_id}/tasks/{task_id}",
            payload,
        )
        return _with_task_link(updated) if not _error(updated) else updated

    @_register_blocking_tool(server)
    def take_task_into_work(task_id: int) -> dict[str, Any]:
        """Перемещает задачу в колонку проекта «В работе» и назначает исполнителем AI-ассистента."""
        task = _api_request("GET", f"/api/tasks/{task_id}")
        if _error(task):
            return task
        project_id = task.get("project_id")
        if project_id is None:
            return {"error": "Task has no project_id"}

        statuses = _project_statuses(project_id)
        if _error(statuses):
            return statuses
        if not statuses:
            return {"error": "This project has no Kanban statuses"}

        progress_terms = (
            "в работе", "в процессе", "выполняется", "in progress", "doing", "active", "progress",
        )
        in_progress = next(
            (
                status for status in statuses
                if status.get("name", "").strip().casefold() in progress_terms
            ),
            None,
        )
        if in_progress is None:
            in_progress = next(
                (
                    status for status in statuses
                    if any(term in status.get("name", "").casefold() for term in progress_terms)
                ),
                None,
            )
        if in_progress is None and len(statuses) > 1:
            first_name = statuses[0].get("name", "").casefold()
            is_intake = any(term in first_name for term in ("к выполнению", "к работе", "todo", "backlog"))
            second_name = statuses[1].get("name", "").casefold()
            is_terminal = any(term in second_name for term in ("готово", "done", "заверш", "выполн", "closed"))
            if is_intake and not is_terminal:
                in_progress = statuses[1]
        if in_progress is None:
            return {
                "error": "Could not determine the in-progress status; choose one of the available statuses",
                "available_statuses": [
                    {"id": item["id"], "name": item["name"]} for item in statuses
                ],
            }

        assignee = _api_request("POST", "/api/assignees/mcp-agent")
        if _error(assignee):
            return assignee
        updated = _api_request(
            "PATCH",
            f"/api/projects/{project_id}/tasks/{task_id}",
            {
                "status_id": in_progress["id"],
                "assignee_email": assignee["email"],
            },
        )
        if _error(updated):
            return updated
        result = _with_task_link(updated)
        result["status_name"] = in_progress["name"]
        result["assignee_email"] = assignee["email"]
        result["assignee_name"] = assignee["name"]
        return result

    @_register_blocking_tool(server)
    def complete_task(task_id: int, result: str | None = None) -> dict[str, Any]:
        """Перемещает задачу в финальную колонку канбана и при необходимости записывает результат."""
        task = _api_request("GET", f"/api/tasks/{task_id}")
        if _error(task):
            return task
        project_id = task.get("project_id")
        if project_id is None:
            return {"error": "Task has no project_id"}

        statuses = _project_statuses(project_id)
        if _error(statuses):
            return statuses
        if not statuses:
            return {"error": "This project has no Kanban statuses"}

        done = next(
            (
                status for status in statuses
                if any(
                    term in status.get("name", "").casefold()
                    for term in ("готово", "done", "заверш", "выполн", "closed", "закрыт")
                )
            ),
            statuses[-1],
        )
        payload: dict[str, Any] = {"status_id": done["id"]}
        if result is not None:
            payload["result"] = result
        updated = _api_request(
            "PATCH",
            f"/api/projects/{project_id}/tasks/{task_id}",
            payload,
        )
        if _error(updated):
            return updated
        completed = _with_task_link(updated)
        completed["status_name"] = done["name"]
        return completed
