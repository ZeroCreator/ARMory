# Интеграция с Kimi Code CLI (MCP)

ARMory можно подключить к [Kimi Code CLI](https://www.kimi.com/code/) через протокол MCP (Model Context Protocol). Это позволяет ассистенту Kimi работать с задачами канбана прямо из терминала: получать задачу по номеру или ссылке, создавать новые задачи и обновлять статус.

Важно: задачи могут относиться к разным проектам. Например, тикет `https://armory.team-73.ru/projects/2/kanban?task=39` создан в ARMory, но доработка выполняется в коде другого проекта (Intraservice). MCP позволяет Kimi прочитать задачу из ARMory и работать с файлами текущего проекта.

## Что умеет интеграция

- `get_task` — получить задачу по `task_id`. Номера задач сквозные, `project_id` можно не указывать.
- `list_tasks` — получить список задач проекта.
- `create_task` — создать новую задачу в проекте.
- `update_task` — обновить задачу (статус, название, описание, приоритет, теги и др.).

## Структура файлов в репозитории ARMory

```
mcp/__init__.py
mcp/mcp_logic.py                     # общая логика MCP (tools, JSON-RPC)
mcp/armory_mcp.py                    # stdio-обёртка (не используется в Kimi 0.28.1)
app/routers/mcp.py                   # HTTP endpoint /mcp
app/config.py                        # настройка MCP_API_KEY
.kimi-code/skills/kanban/SKILL.md    # prompt-скилл для работы с канбаном
.kimi-code/mcp.json.example          # шаблон локальной конфигурации
docs/kimi-mcp.md                     # эта документация
```

## Как работает HTTP MCP

В ARMory backend есть endpoint `POST /mcp`, который принимает JSON-RPC запросы от Kimi Code CLI и делегирует обработку `mcp/mcp_logic.py`. Endpoint доступен сразу при запуске FastAPI-сервера, ничего запускать отдельно не нужно.

Почему HTTP: в Kimi Code CLI 0.28.1 stdio MCP-сервер запускается, но stdin сразу закрывается (`STDIN_CLOSED` в логе), поэтому используется HTTP transport.

Endpoint защищён статичным API-ключом (`MCP_API_KEY`), потому что oauth2-proxy пропускает `/mcp` без браузовой аутентификации.

## Уровни конфигурации

Kimi Code CLI ищет MCP-конфигурацию в двух местах:

- **Project-level**: `.kimi-code/mcp.json` внутри рабочей директории. Работает только в текущем проекте.
- **User-level**: `~/.kimi-code/mcp.json` в домашней директории. Работает из любого проекта.

Project-level конфигурация имеет приоритет над user-level.

## Настройка сервера

1. Сгенерируй ключ:

```bash
openssl rand -hex 32
```

2. Добавь его в `.env` на сервере:

```env
MCP_API_KEY=<сгенерированный-ключ>
```

3. Убедись, что в `compose.gateway.yml` oauth2-proxy пропускает `/mcp`:

```yaml
- OAUTH2_PROXY_SKIP_AUTH_ROUTES=/wopi/.*,/mcp
```

4. Перезапусти ARMory:

```bash
docker compose -f compose.gateway.yml up -d
```

## Настройка для работы из ARMory

Если Kimi открыт в папке ARMory, достаточно project-level конфигурации. Endpoint будет обращаться к локальному серверу.

Скопируй шаблон:

```bash
cp .kimi-code/mcp.json.example .kimi-code/mcp.json
```

И укажи локальный URL и ключ в `.kimi-code/mcp.json`:

```json
{
  "mcpServers": {
    "armory": {
      "url": "http://localhost:8067/mcp",
      "headers": {
        "X-MCP-API-Key": "YOUR_MCP_API_KEY"
      }
    }
  }
}
```

Файл `.kimi-code/mcp.json` исключён из `.gitignore`, потому что содержит локальные настройки.

## Настройка для работы из другого проекта (например, Intraservice)

Чтобы Kimi мог получать задачи ARMory, находясь в другой папке, нужна user-level конфигурация.

Создай файл `~/.kimi-code/mcp.json`:

```json
{
  "mcpServers": {
    "armory": {
      "url": "https://armory.team-73.ru/mcp",
      "headers": {
        "X-MCP-API-Key": "YOUR_MCP_API_KEY"
      }
    }
  }
}
```

Если сервер ARMory доступен локально, используй `http://localhost:8067/mcp`.

Также скопируй skill на user-level:

```bash
mkdir -p ~/.kimi-code/skills/kanban
cp /home/zerocreator/ARMory/.kimi-code/skills/kanban/SKILL.md ~/.kimi-code/skills/kanban/SKILL.md
```

## Проверка endpoint

Проверь, что backend отвечает на JSON-RPC:

```bash
curl -X POST https://armory.team-73.ru/mcp \
  -H "Content-Type: application/json" \
  -H "X-MCP-API-Key: YOUR_MCP_API_KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05"}}'
```

Должен вернуться ответ с `serverInfo`. Без ключа — `401`.

## Перезапуск сессии

MCP-серверы подключаются при старте сессии. После любого изменения конфигурации перезапусти Kimi:

```bash
exit
kimi
```

Проверить подключение можно командой внутри Kimi:

```
/mcp
```

## Использование

### Взять задачу в работу по ссылке из другого проекта

Открой Kimi в папке Intraservice и дай ссылку:

```
https://armory.team-73.ru/projects/2/kanban?task=39
```

Kimi распарсит `task_id=39` (и `project_id=2`, если указан), получит задачу через MCP и начнёт работать с файлами Intraservice в контексте задачи #39.

### По номеру

Номера задач сквозные, поэтому проект можно не указывать:

```
Возьми в работу задачу #39
```

### Через skill

```
/skill:kanban https://armory.team-73.ru/projects/2/kanban?task=39
```

### Создать задачу

```
Создай в проекте ARMory задачу "Исправить отображение дедлайна" со статусом "К выполнению"
```

### Обновить статус

```
Переведи задачу #39 в статус "Тестирование"
```

## Безопасность

- Не хардкоди продакшен URL и креды в коде MCP.
- `MCP_API_KEY` задаётся через переменную окружения `.env` и передаётся в заголовке `X-MCP-API-Key`.
- Не коммить `~/.kimi-code/mcp.json` и `.kimi-code/mcp.json` с секретами.
- OAuth2-proxy должен пропускать `/mcp` без браузовой аутентификации; сама проверка ключа выполняется в приложении.

## Расширение

Чтобы добавить новый инструмент:

1. Опиши инструмент в `TOOLS` в `mcp/mcp_logic.py`.
2. Добавь обработку в `handle_tool_call` в том же файле.
3. При необходимости обнови `.kimi-code/skills/kanban/SKILL.md` и эту документацию.

## Ссылки

- [Документация Kimi Code CLI по MCP](https://www.kimi.com/code/docs/en/kimi-code-cli/customization/mcp.html)
- [Документация Kimi Code CLI по Skills](https://www.kimi.com/code/docs/en/kimi-code-cli/customization/skills.html)
