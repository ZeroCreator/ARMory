# Архитектура ARMory

ARMory — веб-приложение для управления документацией проектов: проекты → разделы → группы → элементы (файлы, заметки, ссылки). Реализовано на Python с использованием FastAPI, SQLAlchemy и Jinja2.

## Стек

- **Backend**: FastAPI + SQLAlchemy 2.0 (async) + aiosqlite
- **Frontend**: Jinja2 templates + Bootstrap 5 + vanilla JS + SortableJS
- **База данных**: SQLite (`data/projectdocs.db`)
- **Хранилище файлов**: локальная файловая система (`data/uploads/`) или S3-совместимое хранилище
- **Документация**: MkDocs + Material

## Структура проекта

```
ARMory/
├── app/                    # Исходный код приложения
│   ├── __init__.py
│   ├── main.py             # Точка входа FastAPI
│   ├── config.py           # Pydantic Settings
│   ├── database.py         # Подключение к БД и фабрика сессий
│   ├── models.py           # SQLAlchemy модели
│   ├── schemas.py          # Pydantic схемы
│   ├── storage.py          # Абстракция хранилища файлов
│   ├── templates/          # Jinja2 шаблоны
│   ├── static/             # CSS, JS, изображения
│   └── routers/            # Модули API и страниц
│       ├── projects.py
│       ├── items.py
│       ├── backups.py
│       ├── scheduler.py
│       ├── calendar.py
│       ├── alexandrite.py
│       └── ...
├── data/                   # Данные приложения
│   ├── projectdocs.db      # База данных
│   ├── uploads/            # Загруженные файлы
│   ├── alexandrite/        # Хранилище Alexandrite (автосоздаётся)
│   └── backups/            # Локальные резервные копии
├── docs/                   # Markdown-документация для MkDocs
├── site/                   # Собранная статика MkDocs
├── scripts/                # Скрипты для планировщика задач
├── backups/                # Пользовательская документация и экспорт
├── lib/                    # Общие shell-скрипты
├── tests/                  # Тесты (pytest)
├── compose.yml             # Docker Compose production
├── compose.dev.yml         # Docker Compose development
├── compose.gateway.yml     # Compose с внешним gateway
├── Dockerfile
├── pyproject.toml
├── uv.lock
└── run.sh                  # Скрипт запуска
```

## Модель данных

```
Project
├── Section
│   ├── Group
│   │   ├── Item (file, note, link)
│   │   └── ItemFile
│   └── Task (scheduler)
└── CalendarEvent
```

### Основные сущности

- **Project** — верхний уровень, соответствует реальному проекту или продукту.
- **Section** — раздел внутри проекта.
- **Group** — группа элементов внутри раздела. Поддерживает ручную сортировку перетаскиванием.
- **Item** — элемент группы: файл, заметка или ссылка. Элементы тоже можно сортировать внутри группы.
- **ItemFile** — история загруженных файлов для элемента, позволяет заменять файл с сохранением названия.
- **Task** — задача планировщика с датами, повторениями и напоминаниями.
- **CalendarEvent** — событие календаря.

## Хранилище файлов

### Локальное хранилище

Файлы сохраняются в `data/uploads/<project_id>_<slug>/`.

При удалении проекта вся его папка удаляется автоматически.

### S3

Поддерживается любое S3-совместимое хранилище. Префикс объектов: `<project_id>_<slug>/`.

## Alexandrite

Отдельное хранилище знаний в формате Markdown с двухпанельным интерфейсом:

- **Локальный режим** — полный доступ: создание, редактирование, переименование, удаление файлов и папок.
- **Режим Яндекс.Диска** — read-only просмотр Markdown-файлов и папок, расположенных в `YANDEX_DISK_ALEXANDRITE_PATH`. Для ограничения корневой папки используется `ALEXANDRITE_YANDEX_ROOT_PATH`.

Состояние дерева (развёрнутые папки) сохраняется в `localStorage` браузера.

## Конфигурация

Конфигурация загружается из переменных окружения и файла `.env` через `pydantic-settings`.

Ключевые параметры:

```python
app_name: str = "ARMory"
database_url: str = "sqlite+aiosqlite:///./projectdocs.db"
storage_type: str = "local"          # local | s3
local_storage_path: str = "./data/uploads"
alexandrite_vault_path: str = "./data/alexandrite"
yandex_disk_path: str = "ARMory/data"
yandex_disk_backups_path: str = "ARMory/backups"
yandex_disk_alexandrite_path: str = "ARMory/alexandrite"
scheduler_enabled: bool = True
```

## Жизненный цикл запроса

1. FastAPI получает HTTP-запрос.
2. Зависимости (`Depends`) предоставляют сессию БД (`AsyncSession`) и бэкенд хранилища (`StorageBackend`).
3. Роутер выполняет бизнес-логику, обращается к БД и/или хранилищу.
4. Jinja2-шаблон рендерит HTML или возвращается JSON.

## Асинхронность

- Все операции с БД выполняются через `AsyncSession`.
- IO-bound операции (S3, Яндекс.Диск) выполняются асинхронно.
- Долгие операции экспорта Alexandrite запускаются в фоновых `asyncio.create_task`.

## Масштабируемость

Текущая архитектура рассчитана на один инстанс. SQLite и локальное хранилище не позволяют запускать несколько реплик без общего хранилища. Для горизонтального масштабирования потребуется:

- PostgreSQL вместо SQLite
- S3 вместо локальной ФС
- Redis или аналог для фоновых задач
