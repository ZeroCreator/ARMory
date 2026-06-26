# Архитектура

## Структура проекта

```
app/
├── main.py           # Точка входа, lifespan, миграции, роутинг страниц
├── config.py         # Pydantic Settings (env-переменные)
├── database.py       # SQLAlchemy async engine + session
├── models.py         # ORM модели
├── schemas.py        # Pydantic схемы для валидации
├── storage.py        # Абстракция хранилища: LocalStorage / S3Storage
├── yandex_disk.py    # Клиент для Яндекс.Диск REST API (sync, backups)
├── routers/
│   ├── projects.py   # CRUD проектов
│   ├── sections.py   # CRUD разделов
│   ├── documents.py  # CRUD групп, items, upload, download, preview
│   ├── sidebar.py    # CRUD блоков и ссылок сайдбара
│   ├── scheduler.py  # Планировщик задач через at
│   ├── calendar.py   # CRUD событий календаря
│   ├── backup.py     # Синхронизация и архивные бэкапы на Яндекс.Диск
│   ├── glossary.py   # CRUD терминов, тем и подтем глоссария
│   └── alexandrite.py # Файловое хранилище заметок
├── templates/        # Jinja2 шаблоны
└── static/           # CSS + JS
```

## Модель данных

### Project
- `id`, `name`, `description`, `sort_order`
- `created_at`, `updated_at`
- связи `sections` и `documents`

### Section (раздел / категория)
- `id`, `project_id`, `name`, `description`, `sort_order`
- связь `documents`

### Document (группа)
- `id`, `project_id`, `section_id` (nullable)
- `title`, `description`, `category`, `sort_order`
- связь `items`

### DocumentItem (ссылка, файл или заметка)
- `id`, `document_id`
- `item_type` (`link` | `file` | `note`), `title`
- `url` — для ссылок
- `file_path`, `file_name`, `file_size`, `mime_type` — для файлов
- `content` — текст заметки

### SidebarBlock / SidebarLink
- Динамические блоки ссылок в левой и правой колонке
- Управляются через API (`/api/sidebar/blocks`)

### CalendarEvent
- `id`, `title`, `description`, `note`
- `start_date`, `end_date`, `all_day`, `color`
- `created_at`
- Таблица создаётся автоматически при старте (миграция в `lifespan`)

### GlossaryTopic / GlossarySubtopic / GlossaryTerm
- Темы и подтемы для группировки терминов.
- Термин содержит `term`, `short_definition`, `definition`, `letter`, связи с темой и подтемой.

### Alexandrite
- Не использует таблицы БД: работает напрямую с файловой системой через `app/routers/alexandrite.py`.
- Корневая папка задаётся через `ALEXANDRITE_VAULT_PATH` (по умолчанию `./data/uploads`).

## Абстракция хранилища

`StorageBackend` — интерфейс с методами `save()`, `delete()`, `get_local_path()`, `get_download_url()`, `get_preview_url()`, `get_public_url()`.

Реализации:

- **LocalStorage** — сохраняет в `./data/uploads/{project_id}_{name}/{doc_id}_{title}/`, отдаёт через `FileResponse`. Папки автоматически переименовываются при смене названия проекта/документа.
- **S3Storage** — загружает в бакет S3, скачивание через **presigned URL** (даже для приватных бакетов)

Переключение через переменную окружения `STORAGE_TYPE=local` или `s3`.

## Синхронизация с Яндекс.Диском

Отдельный модуль `yandex_disk.py` реализует клиент для REST API Яндекс.Диска:
- `upload_file()` / `download_file()` — прямая синхронизация
- `list_files()` / `list_all_files()` — рекурсивный листинг
- `create_folder()` / `ensure_folders()` — создание папок
- `delete()` — удаление файлов и папок

Роутер `backup.py` предоставляет два функционала:
1. **Sync** — прямая синхронизация `projectdocs.db` + `uploads/` ↔ Яндекс.Диск
2. **Archive backups** — создание / восстановление / удаление `.tar.gz` архивов на диске
