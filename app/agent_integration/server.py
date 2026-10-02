"""Общий FastMCP-сервер для транспортов Streamable HTTP и stdio."""

from urllib.parse import urlsplit

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions

from app.config import get_settings
from app.agent_integration.mcp_logic import register_tools
from app.agent_integration.oauth_provider import mcp_oauth_provider


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
    auth_server_provider=mcp_oauth_provider,
    auth=AuthSettings(
        issuer_url=f"{_settings.armory_public_url.rstrip('/')}/mcp",
        resource_server_url=f"{_settings.armory_public_url.rstrip('/')}/mcp",
        required_scopes=["kanban"],
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=["kanban"],
            default_scopes=["kanban"],
        ),
    ),
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
        "Если пользователь дал ссылку вида /projects/{project_id}/kanban?task={task_id}, извлеките task_id и вызовите get_task(task_id); "
        "если project_id из ссылки не совпадает с project_id задачи, остановитесь и сообщите о несоответствии. "
        "После загрузки сообщите номер, название и описание задачи, статус и приоритет; название проекта берите из project_name, "
        "а если поле отсутствует — укажите project_id без предположений. "
        "Для задачи, которую пользователь поручил выполнить, после её создания или загрузки вызовите take_task_into_work(task_id); "
        "затем вносите изменения в текущий проект Codex, который может отличаться от репозитория ARMory. Записывайте ход работы или результат через "
        "update_task. После реализации переводите задачу в «Тестирование». Используйте complete_task только по прямой просьбе пользователя "
        "перевести задачу в финальную колонку. Не переводите задачу в «Деплой» без прямой просьбы пользователя. "
        "Для ручной записи планового времени, времени работы, тестирования или факта в существующую задачу вызывайте update_task_time; "
        "все значения передаются в минутах, пропущенные поля не меняются; если переданы work_minutes или testing_minutes без actual_minutes, "
        "факт пересчитывается как сумма этих этапов. Это задаёт итоги времени и не запускает сессию агента. "
        "Для автоматического учёта активной работы используйте take_task_into_work, start_task_time и pause_task_time. "
        "Исполнителей передавайте отображаемыми именами через assignee_names; email — только внутренний идентификатор API, его не нужно запрашивать у пользователя. "
        "assignee_names задаёт полный список и заменяет текущий: передавайте всех нужных исполнителей. get_task и list_tasks возвращают текущие имена исполнителей. "
        "Если в ответе есть assignee_names_error, не меняйте список исполнителей, пока сопоставление имён не будет исправлено. "
        "При создании задачи назначайте подтверждённого OAuth-пользователя, если он передан MCP-запросом и найден в справочнике исполнителей, и AI Assistant. "
        "Если пользователя не удалось сопоставить по email или имени, всё равно создайте задачу с AI Assistant. "
        "Один MCP_API_KEY не определяет человека: запросы только с этим ключом всё равно создавайте, назначая AI Assistant. "
        "Для HTTP-входа пользователя Codex-клиент должен пройти OAuth-вход в MCP; "
        "локальный stdio-сервер использует MCP_LOCAL_ASSIGNEE_NAME. Дополнительных исполнителей из запроса сохраняйте. "
        "Если в результате create_task поле assignee_prompt_required равно true, сообщите, что задача назначена AI Assistant, и предложите пользователю указать исполнителя. "
        "Если пользователь назовёт исполнителя, получите текущий список через get_task и передайте полный список через update_task.assignee_names, сохранив AI Assistant. "
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
