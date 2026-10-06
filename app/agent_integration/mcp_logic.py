"""MCP-инструменты для создания и управления задачами в канбане ARMory."""

from __future__ import annotations

import asyncio
import mimetypes
from functools import wraps
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlsplit
from uuid import uuid4

import httpx
from mcp.server.fastmcp import Context, FastMCP

from app.auth import get_authenticated_email_from_scope, normalize_email
from app.config import get_settings

_WORKER_INSTANCE_ID = uuid4().hex


def _worker_id(ctx: Context) -> str:
    """Возвращает постоянный идентификатор агента в рамках MCP-сессии."""
    return f"{_WORKER_INSTANCE_ID}-{id(ctx.session)}"


def _start_task_time(task_id: int, phase: Literal["work", "testing"], ctx: Context) -> Any:
    """Запускает интервал работы агента через API ARMory."""
    return _api_request(
        "POST",
        f"/api/tasks/{task_id}/time/start",
        {"worker_id": _worker_id(ctx), "phase": phase},
    )


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


def _input_path_file_name(path: str) -> str:
    parsed = urlsplit(path)
    if parsed.scheme in {"http", "https"}:
        name = Path(unquote(parsed.path)).name
    else:
        name = Path(path).name
    return name or "attachment"


def _upload_task_file(project_id: int, task_id: int, input_path: str) -> dict[str, Any]:
    """Загружает локальный файл или файл по URL во вложение задачи."""
    settings = get_settings()
    headers: dict[str, str] = {}
    mcp_api_key = getattr(settings, "mcp_api_key", None)
    if mcp_api_key:
        headers["Authorization"] = f"Bearer {mcp_api_key}"

    parsed = urlsplit(input_path)
    file_name = _input_path_file_name(input_path)
    content_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    upload_url = f"{_base_url()}/api/projects/{project_id}/tasks/{task_id}/attachments/upload"

    try:
        with httpx.Client(timeout=30.0, trust_env=False) as client:
            if parsed.scheme in {"http", "https"}:
                source_response = client.get(input_path)
                source_response.raise_for_status()
                file_content = source_response.content
                response = client.post(
                    upload_url,
                    data={"title": file_name},
                    files={"file": (file_name, file_content, content_type)},
                    headers=headers,
                )
            else:
                source_path = Path(input_path)
                if not source_path.is_file():
                    return {"error": "Attachment file was not found", "path": input_path}
                with source_path.open("rb") as source_file:
                    response = client.post(
                        upload_url,
                        data={"title": file_name},
                        files={"file": (file_name, source_file, content_type)},
                        headers=headers,
                    )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json()
        except ValueError:
            detail = exc.response.text
        return {"error": f"HTTP {exc.response.status_code}", "detail": detail, "path": input_path}
    except (httpx.HTTPError, OSError, ValueError) as exc:
        return {"error": str(exc), "path": input_path}


def _add_input_paths(task: dict[str, Any], input_paths: list[str] | None) -> dict[str, Any]:
    """Загружает указанные документы во вложения и не дублирует уже загруженные файлы."""
    if not input_paths:
        return task
    result = dict(task)
    attachments = list(task.get("attachments") or [])
    result["attachments"] = attachments
    known_file_names = {
        attachment.get("title")
        for attachment in attachments
        if attachment.get("attachment_type") == "file" and attachment.get("file_path")
    }
    errors = []
    for path in dict.fromkeys(input_paths):
        if not path.strip():
            continue
        file_name = _input_path_file_name(path)
        if file_name in known_file_names:
            continue
        attachment = _upload_task_file(task["project_id"], task["id"], path)
        if _error(attachment):
            errors.append({"path": path, "error": attachment})
        else:
            attachments.append(attachment)
            known_file_names.add(file_name)
    if errors:
        result["input_paths_errors"] = errors
    return result


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


def _resolve_assignee_names(names: list[str]) -> list[str] | dict[str, Any]:
    assignees = _api_request("GET", "/api/assignees")
    if _error(assignees):
        return assignees

    assignees_by_name: dict[str, list[dict[str, str]]] = {}
    for assignee in assignees:
        name = " ".join(assignee.get("name", "").split())
        email = assignee.get("email")
        if name and email:
            assignees_by_name.setdefault(name.casefold(), []).append(assignee)

    resolved_emails = []
    for requested_name in names:
        normalized_name = " ".join(requested_name.split()).casefold()
        matches = assignees_by_name.get(normalized_name, [])
        if not matches:
            return {
                "error": f"Assignee '{requested_name}' was not found",
                "available_assignees": sorted(
                    assignee["name"] for assignee in assignees if assignee.get("name")
                ),
            }
        if len(matches) > 1:
            return {
                "error": (
                    f"Assignee name '{requested_name}' is ambiguous; "
                    "make display names unique in ARMory"
                ),
            }
        resolved_emails.append(matches[0]["email"])

    return list(dict.fromkeys(resolved_emails))


def _assignee_names_by_email() -> dict[str, str] | None:
    assignees = _api_request("GET", "/api/assignees")
    if _error(assignees):
        return None
    return {
        assignee["email"].casefold(): assignee["name"]
        for assignee in assignees
        if assignee.get("email") and assignee.get("name")
    }


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


def _with_task_link(
    task: dict[str, Any],
    assignee_names_by_email: dict[str, str] | None = None,
) -> dict[str, Any]:
    result = dict(task)
    task_id = result.get("id")
    project_id = result.get("project_id")
    if task_id is not None:
        result["task_id"] = task_id
    if task_id is not None and project_id is not None:
        result["url"] = _task_link(project_id, task_id)
    assignee_emails = result.get("assignee_emails") or []
    if not assignee_emails and result.get("assignee_email"):
        assignee_emails = [result["assignee_email"]]
    if assignee_names_by_email is None and assignee_emails:
        assignee_names_by_email = _assignee_names_by_email()
    result["assignee_names"] = [
        assignee_names_by_email[email.casefold()]
        for email in assignee_emails
        if assignee_names_by_email and email.casefold() in assignee_names_by_email
    ]
    if assignee_emails and (
        assignee_names_by_email is None
        or any(email.casefold() not in assignee_names_by_email for email in assignee_emails)
    ):
        result["assignee_names_error"] = (
            "Не удалось сопоставить всех текущих исполнителей с отображаемыми именами; "
            "не меняйте список исполнителей, пока сопоставление не будет исправлено."
        )
    result.pop("assignee_email", None)
    result.pop("assignee_emails", None)
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


def _default_task_assignee_name(ctx: Context) -> tuple[str | None, str | None]:
    settings = get_settings()
    try:
        request = ctx.request_context.request
    except (AttributeError, ValueError):
        request = None
    scope = getattr(request, "scope", None)
    email = ""
    if isinstance(scope, dict):
        authenticated_user = scope.get("user")
        access_token = getattr(authenticated_user, "access_token", None)
        email = normalize_email(getattr(access_token, "user_email", None))
        scope_state = scope.get("state")
        if not email and isinstance(scope_state, dict):
            email = normalize_email(scope_state.get("user_email"))
        if not email:
            email = get_authenticated_email_from_scope(scope, settings)
        if not email and settings.auth_required:
            return None, "authenticated_user_missing"

    if email:
        assignees = _api_request("GET", "/api/assignees")
        if _error(assignees) or not isinstance(assignees, list):
            return None, "assignee_directory_unavailable"
        match = next(
            (
                assignee for assignee in assignees
                if normalize_email(assignee.get("email")) == email
            ),
            None,
        )
        if match is None:
            return None, "authenticated_user_not_in_assignee_directory"
        name = " ".join((match.get("name") or "").split())
        if not name:
            return None, "authenticated_user_display_name_missing"
        return name, None

    local_assignee_name = " ".join((settings.mcp_local_assignee_name or "").split())
    return (
        (local_assignee_name, None)
        if local_assignee_name
        else (None, "local_assignee_not_configured")
    )


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
        """Возвращает задачи проекта ARMory с исполнителями по отображаемым именам."""
        project = _resolve_project(project_id, project_name)
        if _error(project):
            return project
        tasks = _api_request("GET", f"/api/projects/{project['id']}/tasks")
        if _error(tasks):
            return tasks
        assignee_names_by_email = _assignee_names_by_email() or {}
        return {
            "project": {"id": project["id"], "name": project["name"]},
            "tasks": [
                _with_task_link(task, assignee_names_by_email)
                for task in tasks
            ],
            "count": len(tasks),
        }

    @_register_blocking_tool(server)
    def create_task(
        title: str,
        estimated_minutes: int,
        ctx: Context,
        project_name: str | None = None,
        project_id: int | None = None,
        description: str | None = None,
        status_name: str | None = None,
        status_id: int | None = None,
        priority: Literal["low", "medium", "high"] = "medium",
        tags: str | None = None,
        list_name: str | None = None,
        due_date: str | None = None,
        assignee_names: list[str] | None = None,
        input_paths: list[str] | None = None,
    ) -> dict[str, Any]:
        """Создаёт задачу с оценкой и исполнителями; input_paths загружает документы во вложения."""
        if estimated_minutes < 1:
            return {"error": "estimated_minutes must be greater than zero"}

        default_assignee_name, assignee_resolution_error = _default_task_assignee_name(ctx)
        agent_assignee = _api_request("POST", "/api/assignees/mcp-agent")
        if _error(agent_assignee):
            return agent_assignee
        requested_assignees = list(assignee_names or [])
        if default_assignee_name:
            requested_assignees.insert(0, default_assignee_name)
        normalized_assignees = []
        seen_assignees = set()
        for name in requested_assignees:
            normalized = " ".join(name.split())
            key = normalized.casefold()
            if normalized and key not in seen_assignees:
                seen_assignees.add(key)
                normalized_assignees.append(normalized)

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
            "estimated_minutes": estimated_minutes,
        }.items():
            if value is not None:
                payload[key] = value

        resolved_assignees = _resolve_assignee_names(normalized_assignees)
        if _error(resolved_assignees):
            return resolved_assignees
        payload["assignee_emails"] = list(dict.fromkeys([*resolved_assignees, agent_assignee["email"]]))

        task = _api_request("POST", f"/api/projects/{project['id']}/tasks", payload)
        if _error(task):
            return task
        result = _with_task_link(_add_input_paths(task, input_paths))
        result["project_name"] = project["name"]
        result["status_name"] = status["name"]
        result["assignee_prompt_required"] = bool(assignee_resolution_error) and not normalized_assignees
        if assignee_resolution_error:
            result["assignee_resolution_error"] = assignee_resolution_error
        return result

    @_register_blocking_tool(server)
    def get_task(task_id: int) -> dict[str, Any]:
        """Возвращает задачу по глобальному номеру, включая проект и отображаемые имена исполнителей."""
        task = _api_request("GET", f"/api/tasks/{task_id}")
        if _error(task):
            return task
        result = _with_task_link(task)
        project = _resolve_project(task.get("project_id"))
        if not _error(project):
            result["project_name"] = project["name"]
        else:
            result["project_name_error"] = project
        return result

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
        estimated_minutes: int | None = None,
        assignee_names: list[str] | None = None,
        result: str | None = None,
        input_paths: list[str] | None = None,
    ) -> dict[str, Any]:
        """Изменяет поля и исполнителей, загружает input_paths во вложения."""
        task: dict[str, Any] | None = None
        if project_id is None or status_name is not None or status_id is not None:
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
            "estimated_minutes": estimated_minutes,
            "result": result,
        }.items():
            if value is not None:
                payload[key] = value

        if assignee_names is not None:
            resolved_assignees = _resolve_assignee_names(assignee_names)
            if _error(resolved_assignees):
                return resolved_assignees
            payload["assignee_emails"] = resolved_assignees

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

        if not payload and not input_paths:
            return {"error": "No task fields were provided to update"}

        if payload:
            updated = _api_request(
                "PATCH",
                f"/api/projects/{project_id}/tasks/{task_id}",
                payload,
            )
        else:
            updated = task or _api_request("GET", f"/api/tasks/{task_id}")
        if _error(updated):
            return updated
        updated = _add_input_paths(updated, input_paths)
        return _with_task_link(updated)

    @_register_blocking_tool(server)
    def update_task_time(
        task_id: int,
        estimated_minutes: int | None = None,
        work_minutes: int | None = None,
        testing_minutes: int | None = None,
        actual_minutes: int | None = None,
    ) -> dict[str, Any]:
        """Задаёт указанные итоги времени задачи в минутах, не изменяя пропущенные поля."""
        values = {
            "estimated_minutes": estimated_minutes,
            "work_minutes": work_minutes,
            "testing_minutes": testing_minutes,
            "actual_minutes": actual_minutes,
        }
        if all(value is None for value in values.values()):
            return {"error": "Specify at least one task time value in minutes"}
        if any(value is not None and value < 0 for value in values.values()):
            return {"error": "Task time values cannot be negative"}

        task = _api_request("GET", f"/api/tasks/{task_id}")
        if _error(task):
            return task
        project_id = task.get("project_id")
        if project_id is None:
            return {"error": "Could not resolve the task's project_id"}

        payload: dict[str, int] = {}
        if estimated_minutes is not None:
            payload["estimated_minutes"] = estimated_minutes
        for input_name, api_name in (
            ("work_minutes", "work_seconds"),
            ("testing_minutes", "testing_seconds"),
            ("actual_minutes", "actual_seconds"),
        ):
            value = values[input_name]
            if value is not None:
                payload[api_name] = value * 60

        updated = _api_request(
            "PATCH",
            f"/api/projects/{project_id}/tasks/{task_id}",
            payload,
        )
        return updated if _error(updated) else _with_task_link(updated)

    @_register_blocking_tool(server)
    def take_task_into_work(task_id: int, ctx: Context) -> dict[str, Any]:
        """Перемещает задачу в «В работе», добавляет AI Assistant и сохраняет текущих исполнителей."""
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
        assignee_emails = task.get("assignee_emails") or []
        if not assignee_emails and task.get("assignee_email"):
            assignee_emails = [task["assignee_email"]]
        assignee_emails = list(dict.fromkeys([*assignee_emails, assignee["email"]]))
        updated = _api_request(
            "PATCH",
            f"/api/projects/{project_id}/tasks/{task_id}",
            {
                "status_id": in_progress["id"],
                "assignee_emails": assignee_emails,
            },
        )
        if _error(updated):
            return updated
        time_state = _start_task_time(task_id, "work", ctx)
        result = _with_task_link(updated)
        result["status_name"] = in_progress["name"]
        if _error(time_state):
            result["time_tracking_error"] = time_state
        else:
            result["time_tracking_status"] = time_state.get("time_tracking_status", "running")
        return result

    @_register_blocking_tool(server)
    def start_task_time(task_id: int, phase: Literal["work", "testing"], ctx: Context) -> dict[str, Any]:
        """Запускает или возобновляет фазу учёта времени независимо от колонки Kanban."""
        result = _start_task_time(task_id, phase, ctx)
        return result if _error(result) else {"time_tracking": result}

    @_register_blocking_tool(server)
    def pause_task_time(task_id: int, ctx: Context, completed: bool = False) -> dict[str, Any]:
        """Останавливает таймер: completed=True отмечает завершение, False — паузу для ожидания или переключения."""
        result = _api_request(
            "POST",
            f"/api/tasks/{task_id}/time/pause",
            {"worker_id": _worker_id(ctx), "completed": completed},
        )
        return result if _error(result) else {"time_tracking": result}

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
