# ARMory (Арсенал)
Веб-приложение для сбора и управления документами, файлами, ссылками и заметками проектов.

📖 Документация проекта доступна в формате `mkdocs` на **GitHub**:

https://zerocreator.github.io/ARMory/

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

When the auth gateway is enabled, the public port is configured by `GATEWAY_PORT` in `.env` and ARMory itself is no longer exposed directly.

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

MIT
