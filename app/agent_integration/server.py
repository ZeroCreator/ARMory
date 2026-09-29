"""Общий FastMCP-сервер для транспортов Streamable HTTP и stdio."""

from urllib.parse import urlsplit

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.config import get_settings
from app.agent_integration.mcp_logic import register_tools


_settings = get_settings()
_public_url = urlsplit(_settings.armory_public_url)
_public_host = _public_url.netloc
_public_origin = f"{_public_url.scheme}://{_public_url.netloc}"

_allowed_hosts = [
    value for value in (
        _public_host,
        f"{_public_url.hostname}:*" if _public_url.hostname and _public_url.port is None else None,
        "localhost:*",
        "127.0.0.1:*",
        "[::1]:*",
    ) if value
]
_allowed_origins = [
    value for value in (
        _public_origin,
        f"{_public_origin}:*" if _public_url.hostname and _public_url.port is None else None,
        "http://localhost:*",
        "http://127.0.0.1:*",
        "http://[::1]:*",
    ) if value
]

mcp_server = FastMCP(
    name="ARMory Kanban",
    instructions=(
        "Kanban ARMory — система задач, доступная из локальных репозиториев. "
        "Перед созданием задачи вызовите list_projects, если пользователь не указал однозначный проект. "
        "Ответ create_task содержит глобальный task_id и ссылку. Для загрузки задачи по номеру используйте get_task(task_id). "
        "Вызывайте take_task_into_work(task_id) только по просьбе пользователя взять задачу в работу; затем вносите изменения "
        "в текущий проект Codex, который может отличаться от репозитория ARMory. Записывайте ход работы или результат через "
        "update_task. Вызывайте complete_task только по просьбе пользователя завершить задачу."
    ),
    streamable_http_path="/",
    json_response=True,
    stateless_http=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=_allowed_hosts,
        allowed_origins=_allowed_origins,
    ),
)

register_tools(mcp_server)
