import asyncio
from types import SimpleNamespace

import pytest
from mcp.server.fastmcp import FastMCP

from app.agent_integration import mcp_logic


@pytest.fixture
def settings(monkeypatch):
    settings = SimpleNamespace(
        auth_required=False,
        auth_mode="magic_link",
        auth_secret=None,
        mcp_local_assignee_name="  <local-assignee>  ",
        armory_public_url="https://<your-domain>",
    )
    monkeypatch.setattr(mcp_logic, "get_settings", lambda: settings)
    return settings


def make_context(scope):
    request = SimpleNamespace(scope=scope) if scope is not None else None
    return SimpleNamespace(request_context=SimpleNamespace(request=request))


@pytest.mark.parametrize("auth_required", [False, True])
@pytest.mark.parametrize("transport", ["http", "stdio"])
@pytest.mark.parametrize("local_name", ["  <local-assignee>  ", None, " \t "])
def test_default_assignee_depends_on_local_mode(settings, auth_required, transport, local_name):
    settings.auth_required = auth_required
    settings.mcp_local_assignee_name = local_name
    scope = {"headers": [(b"authorization", b"Bearer <mcp-api-key>")]} if transport == "http" else None

    result = mcp_logic._default_task_assignee_name(make_context(scope))

    if transport == "http" and auth_required:
        assert result == (None, "authenticated_user_missing")
    elif local_name and local_name.strip():
        assert result == ("<local-assignee>", None)
    else:
        assert result == (None, "local_assignee_not_configured")


@pytest.mark.parametrize("auth_required", [False, True])
@pytest.mark.parametrize("identity_source", ["oauth", "state", "session"])
def test_authenticated_identity_takes_precedence(settings, monkeypatch, auth_required, identity_source):
    settings.auth_required = auth_required
    email = "<authenticated-email>"
    scope = {"headers": []}
    if identity_source == "oauth":
        scope["user"] = SimpleNamespace(access_token=SimpleNamespace(user_email=email.upper()))
    elif identity_source == "state":
        scope["state"] = {"user_email": email.upper()}
    else:
        monkeypatch.setattr(mcp_logic, "get_authenticated_email_from_scope", lambda *_: email)
    monkeypatch.setattr(
        mcp_logic,
        "_api_request",
        lambda *_: [{"email": email, "name": "  <authenticated-assignee>  "}],
    )

    assert mcp_logic._default_task_assignee_name(make_context(scope)) == (
        "<authenticated-assignee>", None,
    )


@pytest.mark.parametrize(
    ("directory", "error"),
    [
        ({"error": "unavailable"}, "assignee_directory_unavailable"),
        ([], "authenticated_user_not_in_assignee_directory"),
        ([{"email": "<authenticated-email>", "name": " "}], "authenticated_user_display_name_missing"),
    ],
)
def test_authenticated_identity_errors_do_not_assign_local_user(settings, monkeypatch, directory, error):
    scope = {"state": {"user_email": "<authenticated-email>"}}
    monkeypatch.setattr(mcp_logic, "_api_request", lambda *_: directory)

    assert mcp_logic._default_task_assignee_name(make_context(scope)) == (None, error)


@pytest.mark.parametrize("auth_required", [False, True])
@pytest.mark.parametrize("input_paths", [None, ["<project-directory>", "<project-directory>/file with spaces.txt", "<project-directory>"]])
def test_create_task_over_http_assigns_local_user_only_in_local_mode(settings, monkeypatch, auth_required, input_paths):
    settings.auth_required = auth_required
    directory = [
        {"name": "<local-assignee>", "email": "<local-email>"},
        {"name": "AI Assistant", "email": "<agent-email>"},
        {"name": "<additional-assignee>", "email": "<additional-email>"},
    ]
    created_payload = {}
    saved_attachments = []

    def api_request(method, path, json_body=None):
        if method == "GET" and path == "/api/assignees":
            return directory
        if method == "POST" and path == "/api/assignees/mcp-agent":
            return directory[1]
        if method == "GET" and path == "/api/projects":
            return [{"id": 1, "name": "<project-name>"}]
        if method == "GET" and path == "/api/projects/1/task-statuses":
            return [{"id": 2, "name": "К выполнению", "sort_order": 0}]
        if method == "POST" and path == "/api/projects/1/tasks":
            created_payload.update(json_body)
            return {"id": 3, "project_id": 1, **json_body}
        if method == "POST" and path == "/api/projects/1/tasks/3/attachments":
            saved_attachments.append(json_body)
            return {"id": len(saved_attachments), **json_body}
        pytest.fail(f"Unexpected API request: {method} {path}")

    monkeypatch.setattr(mcp_logic, "_api_request", api_request)
    server = FastMCP("<test-server>")
    mcp_logic.register_tools(server)
    tool = server._tool_manager.get_tool("create_task")
    ctx = make_context({"headers": [(b"authorization", b"Bearer <mcp-api-key>")]})

    result = asyncio.run(tool.fn(
        title="<task-title>", estimated_minutes=15, project_id=1, ctx=ctx,
        assignee_names=["<additional-assignee>"],
        input_paths=input_paths,
    ))

    expected_emails = ["<additional-email>", "<agent-email>"]
    expected_names = ["<additional-assignee>", "AI Assistant"]
    if not auth_required:
        expected_emails.insert(0, "<local-email>")
        expected_names.insert(0, "<local-assignee>")
        assert "assignee_resolution_error" not in result
    else:
        assert result["assignee_resolution_error"] == "authenticated_user_missing"
    assert created_payload["assignee_emails"] == expected_emails
    assert result["assignee_names"] == expected_names
    assert result["assignee_prompt_required"] is False
    assert saved_attachments == [
        {"attachment_type": "link", "title": path, "url": path}
        for path in dict.fromkeys(input_paths or [])
    ]
    if input_paths:
        assert len(result["attachments"]) == 2


def test_update_input_paths_preserves_attachments_and_reports_retryable_errors(monkeypatch):
    existing = {"id": 4, "attachment_type": "link", "url": "<project-directory>"}
    task = {"id": 3, "project_id": 1, "status_id": 2, "attachments": [existing]}
    saved = []
    failing_path = "<project-directory>/unavailable.txt"

    def api_request(method, path, json_body=None):
        if method == "GET" and path == "/api/tasks/3":
            return task
        if method == "POST" and path == "/api/projects/1/tasks/3/attachments":
            if json_body["url"] == failing_path:
                return {"error": "HTTP 503"}
            saved.append(json_body)
            return {"id": 5, **json_body}
        pytest.fail(f"Unexpected API request: {method} {path}")

    monkeypatch.setattr(mcp_logic, "_api_request", api_request)
    server = FastMCP("<test-server>")
    mcp_logic.register_tools(server)
    tool = server._tool_manager.get_tool("update_task")
    paths = ["<project-directory>", "<project-directory>/file with spaces.txt", failing_path, " "]
    result = asyncio.run(tool.fn(task_id=3, input_paths=paths))

    assert result["task_id"] == 3
    assert result["attachments"] == [existing, {"id": 5, **saved[0]}]
    assert result["input_paths_errors"] == [{"path": failing_path, "error": {"error": "HTTP 503"}}]
    assert len(saved) == 1
    assert task["attachments"] == [existing]

    task["attachments"] = result["attachments"]
    repeated = asyncio.run(tool.fn(task_id=3, project_id=1, input_paths=paths))
    assert repeated["attachments"] == result["attachments"]
    assert len(saved) == 1


def test_update_task_status_does_not_start_time_phase(monkeypatch):
    requests = []
    task = {
        "id": 3,
        "project_id": 1,
        "status_id": 1,
        "status": {"name": "В работе"},
        "attachments": [],
    }
    updated = {
        "id": 3,
        "project_id": 1,
        "status_id": 2,
        "status": {"name": "Тестирование"},
        "attachments": [],
    }

    def api_request(method, path, json_body=None):
        requests.append((method, path, json_body))
        return task if method == "GET" else updated

    monkeypatch.setattr(mcp_logic, "_api_request", api_request)
    monkeypatch.setattr(mcp_logic, "_task_link", lambda project_id, task_id: "<task-link>")
    server = FastMCP("<test-server>")
    mcp_logic.register_tools(server)
    tool = server._tool_manager.get_tool("update_task")

    result = asyncio.run(tool.fn(task_id=3, status_id=2))

    assert result["status_id"] == 2
    assert requests == [
        ("GET", "/api/tasks/3", None),
        ("PATCH", "/api/projects/1/tasks/3", {"status_id": 2}),
    ]


@pytest.mark.parametrize(
    ("method", "path", "allowed"),
    [
        ("POST", "/api/projects/1/tasks/3/attachments", True),
        ("DELETE", "/api/projects/1/tasks/3/attachments/4", False),
        ("POST", "/api/projects/1/tasks/3/attachments/upload", False),
        ("POST", "/api/projects/1/tasks/3/attachments/4/open", False),
    ],
)
def test_mcp_service_attachment_access_is_limited(method, path, allowed):
    from app.auth import _mcp_service_email

    settings = SimpleNamespace(mcp_api_key="<mcp-api-key>", ai_assignee_email="<agent-email>")
    result = _mcp_service_email(
        {"method": method, "path": path},
        {"authorization": "Bearer <mcp-api-key>"},
        settings,
    )
    assert (result is not None) is allowed


@pytest.mark.parametrize("completed", [False, True])
def test_pause_task_time_passes_explicit_completion_without_changing_kanban(monkeypatch, completed):
    requests = []
    expected_status = "completed" if completed else "paused"

    def api_request(method, path, json_body=None):
        requests.append((method, path, json_body))
        return {"active": False, "time_tracking_status": expected_status}

    monkeypatch.setattr(mcp_logic, "_api_request", api_request)
    monkeypatch.setattr(mcp_logic, "_worker_id", lambda ctx: "<worker-id>")
    server = FastMCP("<test-server>")
    mcp_logic.register_tools(server)
    tool = server._tool_manager.get_tool("pause_task_time")
    result = asyncio.run(tool.fn(task_id=3, ctx=make_context(None), completed=completed))

    assert requests == [("POST", "/api/tasks/3/time/pause", {"worker_id": "<worker-id>", "completed": completed})]
    assert result["time_tracking"]["time_tracking_status"] == expected_status
