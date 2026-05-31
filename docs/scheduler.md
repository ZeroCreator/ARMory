# Планировщик

Планировщик позволяет запускать скрипты по расписанию через системную утилиту `at`.

## Архитектура скриптов

Скрипты вынесены в отдельные проекты вне репозитория ARMory. Путь к проектам задаётся в `ARMory/.env`:

```env
SCRIPTS_PROJECT_PATHS=~/scripts/<project-name>,~/scripts/<another-project>
```

Каждый проект — это папка со своим `.env` и набором скриптов:

```
~/scripts/<project-name>/
├── .env              # переменные окружения + SCHEDULER_TASKS
├── run_task_a.sh
├── run_task_b.sh
└── ...
```

### .env проекта скриптов

```env
# Путь до внешнего проекта (используется вашими скриптами)
PROJECT_DIR=~/path/to/external-project

# Задачи для планировщика
SCHEDULER_TASKS='{
  "task-a": {"name": "Описание задачи A", "script": "run_task_a.sh"},
  "task-b": {"name": "Описание задачи B", "script": "run_task_b.sh"}
}'
```

## Автопрефикс

ARMory автоматически добавляет префикс `имя_папки:` к каждому таску. Например:

- `<project-name>:task-a`
- `<project-name>:task-b`
- `<another-project>:task-c`

Это позволяет безопасно использовать одинаковые ключи в разных проектах.

## API

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/scheduler/tasks` | Список доступных задач |
| POST | `/api/scheduler/schedule` | Запланировать задачу |
| GET | `/api/scheduler/atq` | Список запланированных задач |
| POST | `/api/scheduler/remove-task` | Удалить задачу из очереди |
