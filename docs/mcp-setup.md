# Интеграция через MCP

ARMory можно подключить к любому AI-ассистенту, поддерживающему протокол MCP (Model Context Protocol): Kimi Code CLI, Claude Code, Cline, Continue и другие. Это позволяет ассистенту работать с задачами kanban прямо из терминала или редактора: получать задачу по номеру или ссылке, создавать новые задачи и обновлять статус.

Важно: задачи могут относиться к разным проектам. Например, тикет `https://<armory-domain>/projects/<project-id>/kanban?task=<task-id>` создан в ARMory, но доработка выполняется в другом репозитории. MCP позволяет ассистенту прочитать задачу из ARMory и работать с файлами текущего проекта.

## Что умеет интеграция

- `get_task` — получить задачу по `task_id`. Номера задач сквозные, `project_id` можно не указывать.
- `list_tasks` — получить список задач проекта.
- `create_task` — создать новую задачу в проекте.
- `update_task` — обновить задачу (статус, название, описание, приоритет, теги, результат работы и др.).
- `take_task_into_work` — взять задачу в работу (перевести в статус «В работе» и назначить ответственным AI-ассистента).
- `complete_task` — завершить задачу, при необходимости записав `result` (результат работы).

## Структура файлов в репозитории ARMory

```
mcp/__init__.py
mcp/mcp_logic.py                     # общая логика MCP (tools, JSON-RPC)
mcp/armory_mcp.py                    # stdio-обёртка
app/routers/mcp.py                   # HTTP endpoint /mcp
app/config.py                        # настройка MCP_API_KEY, AI_ASSIGNEE_*
.kimi-code/skills/kanban/SKILL.md    # prompt-скилл для работы с kanban
.kimi-code/mcp.json.example          # шаблон локальной конфигурации
docs/mcp-setup.md                    # эта документация
docs/local-model.md                  # инструкция по локальным моделям
```

## Как работает HTTP MCP

В ARMory backend есть endpoint `POST /mcp`, который принимает JSON-RPC запросы от MCP-клиента и делегирует обработку `mcp/mcp_logic.py`. Endpoint доступен сразу при запуске FastAPI-сервера, ничего запускать отдельно не нужно.

Endpoint защищён статичным API-ключом (`MCP_API_KEY`), потому что oauth2-proxy пропускает `/mcp` без браузовой аутентификации.

## Настройка сервера

1. Сгенерируй ключ:

```bash
openssl rand -hex 32
```

2. Добавь его в `.env` на сервере:

```env
MCP_API_KEY=<сгенерированный-ключ>
```

3. При желании измени имя/email AI-ассистента, от имени которого назначаются задачи:

```env
AI_ASSIGNEE_EMAIL=<ai-assignee-email>
AI_ASSIGNEE_NAME=AI Assistant
```

4. Убедись, что в `compose.gateway.yml` oauth2-proxy пропускает `/mcp`:

```yaml
- OAUTH2_PROXY_SKIP_AUTH_ROUTES=/wopi/.*,/mcp
```

5. Перезапусти ARMory:

```bash
docker compose -f compose.gateway.yml up -d
```

## Настройка MCP-клиента

Большинство MCP-клиентов читают конфигурацию из JSON-файла. Формат похож на:

```json
{
  "mcpServers": {
    "armory": {
      "url": "https://<armory-domain>/mcp",
      "headers": {
        "X-MCP-API-Key": "YOUR_MCP_API_KEY"
      }
    }
  }
}
```

Где разместить файл, зависит от клиента:

- **Kimi Code CLI** — `.kimi-code/mcp.json` в папке проекта или `~/.kimi-code/mcp.json`.
- **Claude Code** — `~/.claude-code/settings.json` или файл настроек проекта.
- **Cline / Continue** — настройки MCP внутри редактора.

Скопируй шаблон и укажи свой URL и ключ:

```bash
cp .kimi-code/mcp.json.example .kimi-code/mcp.json
```

### Инструкция (skill)

Скопируй `.kimi-code/skills/kanban/SKILL.md` в папку скиллов своего MCP-клиента. Например, для Kimi:

```bash
mkdir -p ~/.kimi-code/skills/kanban
cp <armory-project-directory>/.kimi-code/skills/kanban/SKILL.md <mcp-client-skills-directory>/kanban/SKILL.md
```

Этот файл учит ассистента понимать ссылки и номера задач, не закрывать задачу без разрешения, начинать коммиты с `#N` и т.д.

## Примеры фраз

```
Возьми в работу задачу #39
https://<armory-domain>/projects/<project-id>/kanban?task=<task-id>
Покажи задачу #39
Переведи #39 в статус "Тестирование"
Обнови #39 результат "Исправлено отображение дедлайна"
Закрой #39 с результатом "Реализовано в PR #123"
```

## Результат работы и тосты в интерфейсе

- Поле `result` (результат работы) можно передать через `update_task` или `complete_task`.
- Когда задача завершается через `complete_task` или в неё впервые записывается `result` через `update_task`, в открытом kanban появляется тост «Задача №N выполнена».

## Рабочий сценарий из другого проекта

1. Пользователь даёт ссылку на задачу ARMory.
2. Ассистент получает задачу через `mcp__armory__get_task`.
3. Ассистент берёт задачу в работу через `mcp__armory__take_task_into_work` (если пользователь так попросил).
4. Ассистент выполняет изменения в файлах текущего проекта.
5. По окончании ассистент может записать результат через `update_task` или, по явной просьбе пользователя, завершить задачу через `complete_task`.
6. Пользователь видит тост в kanban ARMory, если страница открыта.

## Проверка endpoint

Проверь, что backend отвечает на JSON-RPC:

```bash
curl -X POST https://<armory-domain>/mcp \
  -H "Content-Type: application/json" \
  -H "X-MCP-API-Key: YOUR_MCP_API_KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05"}}'
```

Должен вернуться ответ с `serverInfo`. Без ключа — `401`.

## Перезапуск сессии

MCP-серверы подключаются при старте сессии клиента. После любого изменения конфигурации перезапусти клиент.

## Локальные модели

Чтобы использовать ARMory с локальной моделью (Qwen, Llama и др.), смотри отдельную инструкцию: [docs/local-model.md](local-model.md).

## Безопасность

- Не хардкоди продакшен URL и креды в коде MCP.
- `MCP_API_KEY` задаётся через переменную окружения `.env` и передаётся в заголовке `X-MCP-API-Key`.
- Не коммить файлы MCP-конфигурации с секретами.
- OAuth2-proxy должен пропускать `/mcp` без браузовой аутентификации; сама проверка ключа выполняется в приложении.

## Расширение

Чтобы добавить новый инструмент:

1. Опиши инструмент в `TOOLS` в `mcp/mcp_logic.py`.
2. Добавь обработку в `handle_tool_call` в том же файле.
3. При необходимости обнови `.kimi-code/skills/kanban/SKILL.md` и эту документацию.

## Ссылки

- [Спецификация MCP](https://modelcontextprotocol.io/specification/latest)
- [Kimi Code CLI — MCP](https://www.kimi.com/code/docs/en/kimi-code-cli/customization/mcp.html)
- [Kimi Code CLI — Skills](https://www.kimi.com/code/docs/en/kimi-code-cli/customization/skills.html)
