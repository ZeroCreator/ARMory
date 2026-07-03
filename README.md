# ARMory (Арсенал)

Веб-приложение для сбора и управления документами, файлами, ссылками и заметками проектов.

📖 Документация проекта доступна в формате MkDocs на **GitHub Pages**:

https://zerocreator.github.io/ARMory/

___
## Возможности

- **Проекты и разделы** — создавайте проекты, разбивайте их на разделы и группы документов.
- **Файлы, заметки и ссылки** — храните файлы, текстовые заметки и внешние ссылки в одном месте.
- **Замена файлов** — обновляйте файл, сохраняя его название и историю версий.
- **Сортировка** — меняйте порядок проектов, разделов, групп и элементов перетаскиванием.
- **Поиск** — быстрый поиск по проектам и содержимому.
- **Контекстное меню файлов** — правый клик по элементу открывает меню: копировать ссылку, открыть предпросмотр, открыть в Alexandrite, изменить, скачать, удалить.
- **Alexandrite** — встроенное Markdown-хранилище знаний с двухпанельным редактором:
  - Локальное редактирование файлов и папок.
  - Read-only просмотр заметок с Яндекс.Диска.
  - Поддержка изображений и текстовых файлов.
  - Редактирование офисных документов через Collabora Online.
- **Яндекс.Диск** — синхронизация базы данных, загруженных файлов и Alexandrite с облаком с отображением прогресса операций.
- **Архивные бэкапы** — создание и восстановление архивов `.tar.gz` для ARMory и Alexandrite.
- **Планировщик задач** — задачи с датами, повторениями, приоритетами и напоминаниями.
- **Календарь** — визуальное представление задач и событий по месяцам.
- **Глоссарий** — база терминов с темами, подтемами, импортом и экспортом в `.xlsx`.
- **Адаптивный UI** — Bootstrap 5, сворачиваемые сайдбары, сохранение состояния интерфейса.

___
## Быстрый старт

### Docker (рекомендуется)

```bash
# Production
docker compose up -d

# Production with auth gateway
docker compose -f compose.yml -f compose.gateway.yml up -d --build

# Development (с hot-reload)
docker compose -f compose.yml -f compose.dev.yml up -d
```

Приложение доступно по адресу: http://localhost:<PORT> (порт по умолчанию смотрите в `compose.yml`).

When the auth gateway (oauth2-proxy) is enabled, the public port is configured by `GATEWAY_PORT` in `.env`, ARMory itself is not exposed directly, and the OIDC callback path is `/oauth2/callback`.

### Локальный запуск (без Docker)

Требуется [uv](https://docs.astral.sh/uv/getting-started/installation/):

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port <PORT> --reload
```

### Запуск через systemd

```bash
sudo systemctl enable --now <your-service>.service
```

___
## Разработка документации

Документация построена на [MkDocs](https://www.mkdocs.org/) с темой [Material](https://squidfunk.github.io/mkdocs-material/).

```bash
# Установка зависимостей
uv sync --group dev

# Локальный сервер документации (с автоперезагрузкой)
uv run mkdocs serve --dev-addr 127.0.0.1:<PORT>

# Сборка статики
uv run mkdocs build

# Деплой на GitHub Pages
uv run mkdocs gh-deploy
```

После запуска `mkdocs serve` документация доступна по адресу: `http://127.0.0.1:<PORT>`

___
## Автор

**Shkola Olga**

___
## Лицензия

Все права защищены. Использование, копирование и распространение запрещены без письменного разрешения автора.
