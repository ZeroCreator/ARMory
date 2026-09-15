<div align="center">
  <img src="armory-landing/assets/armory-octopus.png" alt="Маскот ARMory" width="280">

  <h1>ARMory</h1>

  <p><strong>Арсенал инструментов для проектов, документов и рабочих процессов</strong></p>
  <p>Единое веб-приложение для файлов, заметок, задач, знаний и синхронизации.</p>
</div>

<p align="center">
  <a href="docs/index.md">Документация</a> ·
  <a href="#возможности">Возможности</a> ·
  <a href="#быстрый-старт">Быстрый старт</a>
</p>

---

## О проекте

ARMory собирает проектную работу в одном пространстве: документы и ссылки находятся рядом с задачами, заметками, календарём и встроенным хранилищем знаний Alexandrite.

Маскот проекта — осьминог, который символизирует сразу несколько рабочих потоков и помогает держать их под контролем.

## Возможности

| Раздел | Что доступно |
| --- | --- |
| Проекты и документы | Проекты, разделы, группы, файлы, заметки, ссылки, версии и предпросмотр |
| Задачи | Kanban, ToDo, приоритеты, дедлайны, исполнители, вложения и комментарии |
| Планирование | Диаграмма Ганта, календарь, ежедневная сводка и запуск сценариев по расписанию |
| Alexandrite | Двухпанельное Markdown-хранилище знаний, локальные файлы и просмотр данных с Яндекс.Диска |
| Синхронизация | Яндекс.Диск, архивные копии, прогресс операций и восстановление данных |
| Интеграции | MCP для AI-ассистентов, Collabora Online и подключаемые Docker-приложения |
| Интерфейс | Адаптивная вёрстка, Bootstrap 5, сворачиваемые панели и сохранение состояния UI |

## Быстрый старт

### Docker (рекомендуется)

```bash
# Production
docker compose up -d

# Production с auth gateway
docker compose -f compose.yml -f compose.gateway.yml up -d --build

# Development с hot-reload
docker compose -f compose.yml -f compose.dev.yml up -d
```

Приложение будет доступно по адресу `http://<service-host>:<port>`.

При включённом auth gateway публичный порт задаётся переменной `GATEWAY_PORT` в `.env`, а callback-путь OIDC — `/oauth2/callback`.

### Локальный запуск

Требуется [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
uv run uvicorn app.main:app --host <bind-address> --port <port> --reload
```

## Документация

Документация собирается [MkDocs](https://www.mkdocs.org/) с темой [Material](https://squidfunk.github.io/mkdocs-material/) в каталог `site/`.

```bash
uv sync --group dev
uv run mkdocs serve --dev-addr <bind-address>:<port>
uv run mkdocs build
uv run mkdocs gh-deploy
```

## Структура проекта

```text
ARMory/
├── app/                 # веб-приложение
├── armory-landing/      # лендинг и визуальные материалы
├── docs/                # исходники документации
├── compose.yml          # production Compose-конфигурация
└── pyproject.toml       # зависимости и настройки проекта
```

## Лицензия

Все права защищены. Использование, копирование и распространение запрещены без письменного разрешения автора.
