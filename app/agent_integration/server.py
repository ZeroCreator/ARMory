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
        "Kanban ARMory — общая система задач для всех проектов ARMory и всех MCP-клиентов, включая агентов из других репозиториев. "
        "Команду /task ищите где угодно в сообщении пользователя. Если сразу после /task указан номер задачи, "
        "включая необязательный символ # перед цифрами, загрузите именно эту существующую задачу через get_task; "
        "не создавайте вместо неё новую. Если после /task нет номера, создайте новую задачу по описанию запроса. "
        "Без /task и без явной просьбы работать с уже существующим номером задачи карточку автоматически не создавайте. "
        "Для новой задачи сначала вызовите list_projects при необходимости, затем create_task с обязательной плановой оценкой в минутах. "
        "Если пользователь просит выполнить работу, вызовите take_task_into_work и начинайте изменения только после успешного ответа: "
        "вызов назначает AI Assistant и запускает учёт времени. Если пользователь просит только зарегистрировать задачу, "
        "оставьте её в первой колонке и не запускайте учёт. Если создать или взять задачу в работу не удалось, "
        "не начинайте изменения и сообщите пользователю точную ошибку. "
        "Перед созданием задачи вызовите list_projects, если пользователь не указал однозначный проект. "
        "Для каждой новой задачи указывайте реалистичную плановую оценку; передавайте estimated_minutes в минутах. "
        "Ответ create_task содержит глобальный task_id и ссылку. "
        "Для загрузки задачи по номеру используйте get_task(task_id). "
        "Для задачи, которую пользователь поручил выполнить, после её создания или загрузки вызовите take_task_into_work(task_id); "
        "затем вносите изменения в текущий проект Codex, который может отличаться от репозитория ARMory. Записывайте ход работы или результат через "
        "update_task. После реализации переводите задачу в «Тестирование». Используйте complete_task только по прямой просьбе пользователя "
        "перевести задачу в финальную колонку. Не переводите задачу в «Деплой» без прямой просьбы пользователя. "
        "Исполнителей передавайте отображаемыми именами через assignee_names; email — только внутренний идентификатор API, его не нужно запрашивать у пользователя. "
        "assignee_names задаёт полный список и заменяет текущий: передавайте всех нужных исполнителей. get_task и list_tasks возвращают текущие имена исполнителей. "
        "Если в ответе есть assignee_names_error, не меняйте список исполнителей, пока сопоставление имён не будет исправлено. "
        "При создании каждой новой задачи MCP автоматически назначает двух исполнителей: инициатора "
        "(на сервере — пользователя подтверждённой сессии по его имени в справочнике, локально — имя из MCP_LOCAL_ASSIGNEE_NAME) "
        "и AI Assistant. Дополнительных исполнителей из запроса пользователя сохраняйте. "
        "Когда пользователь поручает задачу агенту, вызывайте take_task_into_work: добавляйте AI Assistant, сохраняя всех текущих исполнителей, "
        "и переводите задачу в «В работе». Этот вызов запускает учёт рабочего времени. При переводе задачи в «Тестирование» "
        "учёт переключается на тестирование; при переходе в другой статус интервал закрывается. При переключении агента на новую задачу "
        "предыдущий интервал автоматически закрывается. Перед возвратом пользователю или длительной паузой вызывайте pause_task_time; "
        "после возобновления вызывайте start_task_time с фазой «work» или «testing»."
    ),
    streamable_http_path="/",
    json_response=True,
    stateless_http=False,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=_allowed_hosts,
        allowed_origins=_allowed_origins,
    ),
)

register_tools(mcp_server)
