# PocketBase

PocketBase встроен в ARMory как инструмент для управления схемами данных проектов. Доступ к админке осуществляется через меню ARMory.

## Структура

Каждый проект может иметь свой изолированный PocketBase-инстанс:

```text
data/
├── pb_data/
│   └── <project>/          # SQLite-базы и файлы проекта
└── pb_migrations/
    └── <project>/          # JS-миграции схемы проекта
```

## Конфигурация

Переменные окружения (см. `.env.example`):

```env
POCKETBASE_PROJECTS=intraservice,armory
POCKETBASE_DEFAULT_PROJECT=intraservice
POCKETBASE_BASE_PORT=8091
POCKETBASE_INTERNAL_URL=http://pocketbase:8090
POCKETBASE_ADMIN_EMAIL=admin@example.com
POCKETBASE_ADMIN_PASSWORD=<пароль>
```

- `POCKETBASE_PROJECTS` — список проектов через запятую.
- `POCKETBASE_DEFAULT_PROJECT` — проект по умолчанию.
- `POCKETBASE_BASE_PORT` — базовый порт; проекты получают порты `8091`, `8092` и т.д.
- `POCKETBASE_ADMIN_EMAIL` / `POCKETBASE_ADMIN_PASSWORD` — суперпользователь, создаётся автоматически.

## Локальный запуск

Проще всего запустить оба сервиса одной командой:

```bash
./run-dev.sh
```

Скрипт поднимет PocketBase в фоне, экспортирует `POCKETBASE_INTERNAL_URL=http://127.0.0.1:8090` и запустит ARMory с hot-reload на порту `8067`.

Если нужно запускать вручную:

```bash
# терминал 1
./pocketbase/run-pocketbase.sh
```

```bash
# терминал 2
export POCKETBASE_INTERNAL_URL=http://127.0.0.1:8090
uv run uvicorn app.main:app --host 0.0.0.0 --port 8067 --reload
```

## Docker

PocketBase запускается вместе с остальными сервисами:

```bash
docker compose up -d --build
```

ARMory проксирует запросы с `/pocketbase/<project>/` на соответствующий PocketBase-инстанс.

## Автозагрузка на локальной машине

Если ARMory уже стартует через systemd, PocketBase можно запустить отдельным user-сервисом:

```bash
# Скопировать юнит
mkdir -p ~/.config/systemd/user
cp armory-pocketbase.service ~/.config/systemd/user/

# Указать свои учётные данные (опционально)
systemctl --user edit armory-pocketbase.service
# В открывшемся редакторе добавить:
# [Service]
# Environment=POCKETBASE_ADMIN_EMAIL=admin@example.com
# Environment=POCKETBASE_ADMIN_PASSWORD=your-password

systemctl --user daemon-reload
systemctl --user enable --now armory-pocketbase.service
```

После перезагрузки PocketBase поднимется автоматически на `http://127.0.0.1:8090`, а ARMory продолжит проксировать его через `/pocketbase/_/`. Статус проверить командой:

```bash
systemctl --user status armory-pocketbase.service
```

## Доступ к админке

1. Открой ARMory.
2. В меню выбери проект в разделе **PocketBase**.
3. Войди под суперпользователем (`POCKETBASE_ADMIN_EMAIL` / `POCKETBASE_ADMIN_PASSWORD`).

После входа доступна админка с коллекциями, схемой и ERD-диаграммой.

## Перенос данных между машинами

Скопируй директории проекта:

```bash
rsync -av source/data/pb_data/<project>/ data/pb_data/<project>/
rsync -av source/data/pb_migrations/<project>/ data/pb_migrations/<project>/
```

## Ограничения

- PocketBase не умеет переключать проекты внутри одной админки. Каждый проект — отдельный инстанс.
- Порядок проектов в `POCKETBASE_PROJECTS` влияет на назначение портов; меняйте его осторожно.
