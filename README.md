# ARMory

Веб-приложение для сбора и управления документами, файлами, ссылками и заметками проектов.

## Возможности

- **Проекты** — создавайте проекты и собирайте в них документы с описаниями
- **Разделы** — группируйте документы внутри проекта по категориям
- **Ссылки** — добавляйте ссылки на внешние ресурсы (Google Drive, Excel Online, Google Docs, YouTube, Figma, Notion, GitHub и т.д.) с автоматическим определением типа
- **Файлы** — загружайте файлы напрямую в приложение. Файлы хранятся в структурированном дереве папок: `{project_id}_{имя}/{doc_id}_{название}/`
- **Заметки** — создавайте текстовые заметки (notes) прямо в документе
- **Предпросмотр** — открывайте изображения, PDF, видео и аудио без скачивания
- **Сайдбар** — динамические блоки ссылок в левой и правой колонке, управляемые через БД
- **Планировщик** — запускайте скрипты Dogma и TrendAgent по расписанию через `at`
- **Хранилище** — поддержка локального хранилища или S3 (MinIO, AWS S3, Yandex Cloud и др.)
- **Скачивание** — скачивайте загруженные файлы обратно (для S3 — через presigned URL)

## Архитектура

```
app/
├── main.py           # Точка входа, lifespan, миграции, роутинг страниц
├── config.py         # Pydantic Settings (env-переменные)
├── database.py       # SQLAlchemy async engine + session
├── models.py         # ORM модели: Project, Section, Document, DocumentItem, SidebarBlock, SidebarLink
├── schemas.py        # Pydantic схемы для валидации
├── storage.py        # Абстракция хранилища: LocalStorage / S3Storage
├── routers/
│   ├── projects.py   # CRUD проектов
│   ├── sections.py   # CRUD разделов
│   ├── documents.py  # CRUD групп, items, upload, download, preview
│   ├── sidebar.py    # CRUD блоков и ссылок сайдбара
│   └── scheduler.py  # Планировщик задач через at
├── templates/        # Jinja2 шаблоны
└── static/           # CSS + JS
```

### Стек

- **Backend**: FastAPI + SQLAlchemy 2.0 (async) + SQLite
- **Frontend**: Server-side rendering (Jinja2) + Bootstrap 5 + Vanilla JS
- **Storage**: локальная файловая система (структурированные подпапки) или S3-совместимое хранилище
- **Package Manager**: [uv](https://docs.astral.sh/uv/) — современный менеджер от создателей `ruff`

### Модель данных

**Project**
- `id`, `name`, `description`, `sort_order`
- `created_at`, `updated_at`
- связи `sections` и `documents`

**Section** (раздел / категория)
- `id`, `project_id`, `name`, `description`, `sort_order`
- связь `documents`

**Document** (группа)
- `id`, `project_id`, `section_id` (nullable)
- `title`, `description`, `category`, `sort_order`
- связь `items`

**DocumentItem** (ссылка, файл или заметка)
- `id`, `document_id`
- `item_type` (`link` | `file` | `note`), `title`
- `url` — для ссылок
- `file_path`, `file_name`, `file_size`, `mime_type` — для файлов
- `content` — текст заметки

**SidebarBlock** / **SidebarLink**
- Динамические блоки ссылок в левой и правой колонке
- Управляются через API (`/api/sidebar/blocks`)

### Абстракция хранилища

`StorageBackend` — интерфейс с методами `save()`, `delete()`, `get_local_path()`, `get_download_url()`, `get_preview_url()`, `get_public_url()`.

Реализации:
- `LocalStorage` — сохраняет в `./data/uploads/{project_id}_{name}/{doc_id}_{title}/`, отдаёт через `FileResponse`. Папки автоматически переименовываются при смене названия проекта/документа.
- `S3Storage` — загружает в бакет S3, скачивание через **presigned URL** (даже для приватных бакетов)

Переключение через переменную окружения `STORAGE_TYPE=local` или `s3`.

## Установка и запуск

### Docker (рекомендуется для production и локального развёртывания)

```bash
# Production (без hot-reload)
docker compose up -d

# Development (с hot-reload, код пробрасывается из хоста)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

Данные (SQLite + uploads) сохраняются в `./data/` на хосте.

Приложение доступно по адресу: http://localhost:8088 (или порту из переменной `PORT`)

### Локальный запуск (без Docker)

Требуется [uv](https://docs.astral.sh/uv/getting-started/installation/):

```bash
# Автоматический запуск (uv сам создаст .venv, установит зависимости и запустит сервер)
uv run uvicorn app.main:app --host 0.0.0.0 --port 8088 --reload

# Или через скрипт
chmod +x run.sh
./run.sh
```

### Запуск через systemd

```bash
sudo systemctl enable --now armory-app.service
```

Сервис слушает порт `5005` (настраивается в `/etc/systemd/system/armory-app.service`).

### Добавление dev-зависимостей

```bash
# Тесты и утилиты разработчика устанавливаются через группу dev
uv sync --group dev
```

## Подключение S3

Приложение поддерживает любое S3-совместимое хранилище. Для переключения на S3:

```bash
cp .env.example .env
# отредактируй .env
```

### Общие параметры

```env
STORAGE_TYPE=s3
S3_BUCKET_NAME=my-docs-bucket
S3_ACCESS_KEY_ID=YOUR_KEY
S3_SECRET_ACCESS_KEY=YOUR_SECRET
S3_REGION=ru-central1

# Endpoint URL (пустой для AWS)
S3_ENDPOINT_URL=https://storage.yandexcloud.net

# Path-style addressing (True для MinIO, False для облачных провайдеров)
S3_FORCE_PATH_STYLE=False

# Время жизни presigned-ссылки в секундах (по умолчанию 1 час)
S3_PRESIGNED_EXPIRES=3600
```

### Примеры для провайдеров

#### Yandex Cloud

```env
S3_ENDPOINT_URL=https://storage.yandexcloud.net
S3_REGION=ru-central1
S3_BUCKET_NAME=my-bucket
S3_ACCESS_KEY_ID=<идентификатор_ключа>
S3_SECRET_ACCESS_KEY=<секретный_ключ>
S3_FORCE_PATH_STYLE=False
```

Ключи создаются в [Yandex Cloud Console](https://console.cloud.yandex.ru/) → Сервисные аккаунты → Создать ключ доступа.

#### AWS S3

```env
S3_ENDPOINT_URL=              # оставь пустым!
S3_REGION=eu-west-1
S3_BUCKET_NAME=my-bucket
S3_ACCESS_KEY_ID=AKIA...
S3_SECRET_ACCESS_KEY=...
S3_FORCE_PATH_STYLE=False
```

Ключи — в AWS IAM → Users → Security credentials → Access keys.

#### MinIO (self-hosted / Docker)

```env
S3_ENDPOINT_URL=http://localhost:9000
S3_REGION=us-east-1
S3_BUCKET_NAME=projectdocs
S3_ACCESS_KEY_ID=minioadmin
S3_SECRET_ACCESS_KEY=minioadmin
S3_FORCE_PATH_STYLE=True
```

Запуск MinIO в Docker:

```bash
docker run -p 9000:9000 -p 9001:9001 \
  -e MINIO_ROOT_USER=minioadmin \
  -e MINIO_ROOT_PASSWORD=minioadmin \
  minio/minio server /data --console-address ":9001"
```

Создай бакет через MinIO Console (http://localhost:9001) или `mc mb`.

#### Selectel

```env
S3_ENDPOINT_URL=https://s3.selcloud.ru
S3_REGION=ru-1
S3_BUCKET_NAME=my-bucket
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
S3_FORCE_PATH_STYLE=False
```

### Как это работает

1. **Загрузка**: файл через `boto3.upload_fileobj()` попадает в S3-бакет под уникальным ключом `uploads/{uuid}.{ext}`
2. **Скачивание**: приложение генерирует **presigned URL** через `generate_presigned_url()` с заголовком `Content-Disposition: attachment`. Это работает даже если бакет приватный — ссылка действует `S3_PRESIGNED_EXPIRES` секунд.
3. **Удаление**: при удалении документа из проекта файл удаляется из S3 через `delete_object()`.

## API Endpoints

### Проекты

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/projects` | Список проектов |
| POST | `/api/projects` | Создать проект |
| GET | `/api/projects/{id}` | Детали проекта |
| PATCH | `/api/projects/{id}` | Обновить проект |
| DELETE | `/api/projects/{id}` | Удалить проект (+ файлы из хранилища) |

### Разделы

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/projects/{id}/sections` | Разделы проекта |
| POST | `/api/projects/{id}/sections` | Создать раздел |
| PATCH | `/api/projects/{id}/sections/reorder` | Изменить порядок разделов |
| PATCH | `/api/projects/{id}/sections/{sec_id}` | Переименовать / обновить раздел |
| DELETE | `/api/projects/{id}/sections/{sec_id}` | Удалить раздел (группы переходят в "Без раздела") |

### Документы и файлы

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/projects/{id}/documents` | Группы без раздела |
| POST | `/api/projects/{id}/documents` | Создать группу |
| PATCH | `/api/projects/{id}/documents/{doc_id}` | Обновить группу / переместить в раздел |
| DELETE | `/api/projects/{id}/documents/{doc_id}` | Удалить группу (+ файлы из хранилища) |
| POST | `/api/projects/{id}/documents/{doc_id}/items` | Добавить ссылку, файл или заметку |
| PATCH | `/api/projects/{id}/documents/{doc_id}/items/{item_id}` | Редактировать item |
| DELETE | `/api/projects/{id}/documents/{doc_id}/items/{item_id}` | Удалить item (+ файл из хранилища) |
| GET | `/api/projects/{id}/documents/{doc_id}/items/{item_id}/download` | Скачать файл |
| GET | `/api/projects/{id}/documents/{doc_id}/items/{item_id}/preview` | Предпросмотр файла |

### Сайдбар

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/sidebar/blocks` | Список блоков сайдбара |
| POST | `/api/sidebar/blocks` | Создать блок |
| PATCH | `/api/sidebar/blocks/{id}` | Обновить блок |
| DELETE | `/api/sidebar/blocks/{id}` | Удалить блок (+ ссылки) |
| POST | `/api/sidebar/blocks/{id}/links` | Добавить ссылку в блок |
| PATCH | `/api/sidebar/links/{id}` | Обновить ссылку |
| DELETE | `/api/sidebar/links/{id}` | Удалить ссылку |

### Планировщик

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/scheduler/schedule` | Запланировать задачу |
| GET | `/api/scheduler/atq` | Список запланированных задач |
| POST | `/api/scheduler/remove-task` | Удалить задачу из очереди |

## Бэкапы

### Что бэкапить

Все данные хранятся в двух местах:
- `data/projectdocs.db` — база данных SQLite (проекты, разделы, группы, ссылки, метаданные файлов)
- `data/uploads/` — загруженные файлы (структурированные по папкам проектов и документов)

### Ручной бэкап

```bash
# В корне проекта
cd ~/ARMory
tar -czvf backup_$(date +%Y%m%d_%H%M%S).tar.gz data/projectdocs.db data/uploads/
```

Получится архив вида `backup_20260520_143052.tar.gz`.

### Восстановление из бэкапа

```bash
# Распаковать в корень проекта
cd ~/ARMory
tar -xzvf backup_20260520_143052.tar.gz
```

### Автоматический бэкап (cron)

Добавь в crontab:

```bash
# Каждый день в 3:00 утра
crontab -e
0 3 * * * cd /home/zerocreator/ARMory && tar -czf /home/zerocreator/backups/armory_$(date +\%Y\%m\%d).tar.gz data/projectdocs.db data/uploads/ >/dev/null 2>&1
```

### Бэкап при деплое на другой сервер

```bash
# На исходной машине
tar -czvf backup_$(date +%Y%m%d_%H%M%S).tar.gz data/projectdocs.db data/uploads/ .env

# На новом сервере
mkdir -p /opt/ARMory && cd /opt/ARMory
# Распакуй проект + данные
tar -xzvf backup_20260520_143052.tar.gz
# Запуск
docker compose up -d --build
```

## Автор

**Shkola Olga**

## Лицензия

MIT

---

ARMory © 2026 Shkola Olga
