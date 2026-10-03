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
def test_create_task_over_http_assigns_local_user_only_in_local_mode(settings, monkeypatch, auth_required):
    settings.auth_required = auth_required
    directory = [
        {"name": "<local-assignee>", "email": "<local-email>"},
        {"name": "AI Assistant", "email": "<agent-email>"},
        {"name": "<additional-assignee>", "email": "<additional-email>"},
    ]
    created_payload = {}

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
        pytest.fail(f"Unexpected API request: {method} {path}")

    monkeypatch.setattr(mcp_logic, "_api_request", api_request)
    server = FastMCP("<test-server>")
    mcp_logic.register_tools(server)
    tool = server._tool_manager.get_tool("create_task")
    ctx = make_context({"headers": [(b"authorization", b"Bearer <mcp-api-key>")]})

    result = asyncio.run(tool.fn(
        title="<task-title>", estimated_minutes=15, project_id=1, ctx=ctx,
        assignee_names=["<additional-assignee>"],
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
