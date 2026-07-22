# Интеграция с Kimi Code CLI (MCP)

ARMory можно подключить к [Kimi Code CLI](https://www.kimi.com/code/) через протокол MCP (Model Context Protocol). Это позволяет ассистенту Kimi работать с задачами канбана прямо из терминала: получать задачу по номеру или ссылке, создавать новые задачи и обновлять статус.

## Что умеет интеграция

- `get_task` — получить задачу по `project_id` и `task_id`.
- `list_tasks` — получить список задач проекта.
- `create_task` — создать новую задачу в проекте.
- `update_task` — обновить задачу (статус, название, описание, приоритет, теги и др.).

## Структура файлов

```
.kimi-code/mcp.json              # конфигурация MCP-сервера (локальная, не в git)
.kimi-code/mcp.json.example      # шаблон конфигурации
.kimi-code/skills/kanban/SKILL.md  # prompt-скилл для работы с канбаном (в git)
mcp/armory_mcp.py                # сам MCP-сервер (stdio)
AGENTS.md                        # локальные правила для Kimi (не в git)
```

## Настройка

### 1. Базовый URL API

Открой `.kimi-code/mcp.json` и укажи адрес API ARMory:

```json
{
  "mcpServers": {
    "armory": {
      "command": ".venv/bin/python",
      "args": ["mcp/armory_mcp.py"],
      "env": {
        "ARMORY_BASE_URL": "https://armory.team-73.ru"
      }
    }
  }
}
```

При локальной разработке используй `http://localhost:8067`.

### 2. Запуск MCP-сервера

Сервер запускается автоматически Kimi Code CLI при старте новой сессии. Если `.kimi-code/mcp.json` изменялся, перезапусти сессию:

```bash
exit
kimi
```

Проверить, что сервер подключился, можно командой внутри Kimi:

```
/mcp
```

## Использование

### Взять задачу в работу по номеру

```
Возьми в работу задачу #39 в проекте ARMory
```

Kimi вызовет `mcp__armory__get_task`, получит задачу и будет работать в её контексте.

### По ссылке

```
https://armory.team-73.ru/projects/2/kanban?task=39
```

Kimi распарсит `project_id=2` и `task_id=39` и подтянет задачу.

### Через skill

```
/skill:kanban #39
```

Или:

```
/skill:kanban https://armory.team-73.ru/projects/2/kanban?task=39
```

### Создать задачу

```
Создай в проекте ARMory задачу "Исправить отображение дедлайна" со статусом "К выполнению"
```

Kimi вызовет `mcp__armory__create_task` с нужными параметрами.

### Обновить статус

```
Переведи задачу #39 в статус "Тестирование"
```

Kimi вызовет `mcp__armory__update_task`.

## Безопасность

- Не хардкоди продакшен URL и креды в `mcp/armory_mcp.py`.
- Для продакшена передавай `ARMORY_BASE_URL` через `.kimi-code/mcp.json` или переменные окружения.
- Если API ARMory требует авторизации, добавь передачу токена в заголовках `mcp/armory_mcp.py` (например, через `ARMORY_API_TOKEN`).
- Файл `.kimi-code/mcp.json` может содержать локальные настройки; не коммить в него секреты.

## Расширение

Чтобы добавить новый инструмент, отредактируй `mcp/armory_mcp.py`:

1. Опиши инструмент в `handle_tools_list`.
2. Добавь обработку в `handle_tool_call`.
3. При необходимости обнови `AGENTS.md`.

## Ссылки

- [Документация Kimi Code CLI по MCP](https://www.kimi.com/code/docs/en/kimi-code-cli/customization/mcp.html)
- [Документация Kimi Code CLI по Skills](https://www.kimi.com/code/docs/en/kimi-code-cli/customization/skills.html)
