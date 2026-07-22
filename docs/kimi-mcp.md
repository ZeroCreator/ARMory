# Интеграция с Kimi Code CLI (MCP)

ARMory можно подключить к [Kimi Code CLI](https://www.kimi.com/code/) через протокол MCP (Model Context Protocol). Это позволяет ассистенту Kimi работать с задачами канбана прямо из терминала: получать задачу по номеру или ссылке, создавать новые задачи и обновлять статус.

Важно: задачи могут относиться к разным проектам. Например, тикет `https://armory.team-73.ru/projects/2/kanban?task=39` создан в ARMory, но доработка выполняется в коде другого проекта (Intraservice). MCP позволяет Kimi прочитать задачу из ARMory и работать с файлами текущего проекта.

## Что умеет интеграция

- `get_task` — получить задачу по `project_id` и `task_id`.
- `list_tasks` — получить список задач проекта.
- `create_task` — создать новую задачу в проекте.
- `update_task` — обновить задачу (статус, название, описание, приоритет, теги и др.).

## Структура файлов в репозитории ARMory

```
mcp/armory_mcp.py                    # MCP-сервер (stdio)
.kimi-code/skills/kanban/SKILL.md    # prompt-скилл для работы с канбаном
.kimi-code/mcp.json.example          # шаблон локальной конфигурации
docs/kimi-mcp.md                     # эта документация
```

## Уровни конфигурации

Kimi Code CLI ищет MCP-конфигурацию в двух местах:

- **Project-level**: `.kimi-code/mcp.json` внутри рабочей директории. Работает только в текущем проекте.
- **User-level**: `~/.kimi-code/mcp.json` в домашней директории. Работает из любого проекта.

MCP-сервер (`mcp/armory_mcp.py`) лежит в репозитории ARMory. Чтобы Kimi мог запустить его из другого проекта, в `~/.kimi-code/mcp.json` нужно указать **абсолютные пути**.

## Настройка для работы из ARMory

Если Kimi открыт в папке ARMory, достаточно project-level конфигурации.

Скопируй шаблон:

```bash
cp .kimi-code/mcp.json.example .kimi-code/mcp.json
```

И укажи нужный URL в `.kimi-code/mcp.json`:

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

Файл `.kimi-code/mcp.json` исключён из `.gitignore`, потому что содержит локальные настройки.

## Настройка для работы из другого проекта (например, Intraservice)

Чтобы Kimi мог получать задачи ARMory, находясь в другой папке, нужна user-level конфигурация.

Создай файл `~/.kimi-code/mcp.json`:

```json
{
  "mcpServers": {
    "armory": {
      "command": "/home/zerocreator/ARMory/.venv/bin/python",
      "args": ["/home/zerocreator/ARMory/mcp/armory_mcp.py"],
      "env": {
        "ARMORY_BASE_URL": "https://armory.team-73.ru"
      }
    }
  }
}
```

Замени пути на актуальные для твоей машины.

Также скопируй skill на user-level:

```bash
mkdir -p ~/.kimi-code/skills/kanban
cp /home/zerocreator/ARMory/.kimi-code/skills/kanban/SKILL.md ~/.kimi-code/skills/kanban/SKILL.md
```

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

Kimi распарсит `project_id=2` и `task_id=39`, получит задачу через MCP и начнёт работать с файлами Intraservice в контексте задачи #39.

### По номеру

```
Возьми в работу задачу #39 из проекта 2
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

- Не хардкоди продакшен URL и креды в `mcp/armory_mcp.py`.
- Передавай `ARMORY_BASE_URL` через `mcp.json` или переменные окружения.
- Если API ARMory требует авторизации, добавь передачу токена в заголовках `mcp/armory_mcp.py` (например, через `ARMORY_API_TOKEN`).
- Не коммить `~/.kimi-code/mcp.json` и `.kimi-code/mcp.json` с секретами.

## Расширение

Чтобы добавить новый инструмент, отредактируй `mcp/armory_mcp.py`:

1. Опиши инструмент в `handle_tools_list`.
2. Добавь обработку в `handle_tool_call`.
3. При необходимости обнови `.kimi-code/skills/kanban/SKILL.md` и эту документацию.

## Ссылки

- [Документация Kimi Code CLI по MCP](https://www.kimi.com/code/docs/en/kimi-code-cli/customization/mcp.html)
- [Документация Kimi Code CLI по Skills](https://www.kimi.com/code/docs/en/kimi-code-cli/customization/skills.html)
