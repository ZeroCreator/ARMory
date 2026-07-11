# PocketBase

PocketBase — это встроенное расширение ARMory для коллективной работы над проектами. Оно запускается как отдельный сервис рядом с ARMory и не заменяет основную базу данных.

## Что даёт интеграция

- **Комментарии к проектам** — обсуждение внутри страницы проекта.
- **Задачи по проекту** — отслеживание статуса работ.
- **Wiki-заметки команды** — общие заметки и решения.
- **Формы для сбора данных** — баг-репорты, предложения, фидбек.
- **Лента активности** — кто и когда что-то изменил.

## Включение PocketBase

1. В `.env` установить:

   ```env
   POCKETBASE_ENABLED=true
   # Для Docker: http://pocketbase:8090
   # Для локального запуска: http://127.0.0.1:8090
   POCKETBASE_URL=http://127.0.0.1:8090
   POCKETBASE_PUBLIC_URL=http://127.0.0.1:8090
   POCKETBASE_ADMIN_EMAIL=admin@example.com
   POCKETBASE_ADMIN_PASSWORD=changeme
   ```

2. Запустить PocketBase:

   **Вариант А — локально без Docker (бинарник рядом с проектом):**

   Распакуй бинарник в папку `./pocketbase` (она уже в `.gitignore`, не попадёт в Git):
   ```bash
   unzip ~/downloads/pocketbase_0.39.6_linux_amd64.zip -d ./pocketbase
   ```

   Запусти скрипт:
   ```bash
   ./scripts/run_pocketbase.sh
   ```

   Скрипт автоматически создаст/обновит администратора из `.env` и стартанёт сервер на `http://127.0.0.1:8090`.

   **Вариант Б — через Docker Compose (прод):**
   ```bash
   docker compose up -d
   ```

   **Вариант В — через Docker Compose (локальная разработка):**
   ```bash
   docker compose -f compose.yml -f compose.dev.yml up -d
   ```

3. В меню ARMory появится ссылка **PocketBase**.

## Первый запуск и создание админа

После старта PocketBase доступен по адресу из `POCKETBASE_PUBLIC_URL`.

**Docker:** администратор создаётся/обновляется автоматически при каждом старте контейнера.

**Локально без Docker:** администратор создаётся/обновляется автоматически скриптом `scripts/run_pocketbase.sh`.

Если PocketBase запущен вручную, создать администратора можно через CLI:

```bash
./pocketbase/pocketbase superuser create admin@example.com changeme --dir=./data/pb_data
```

Или через веб-интерфейс:

1. Откройте `http://127.0.0.1:8090/_/`. 
2. Создайте администратора с email и паролем из `.env`.

   > Email/пароль из `.env` используются ARMory для авторизации. Токен можно оставить пустым.

3. Если хотите использовать готовый токен, скопируйте его в админке и вставьте в `.env`:

   ```env
   POCKETBASE_ADMIN_TOKEN=<токен>
   ```

4. Перезапустите ARMory.

   **Локально:**
   ```bash
   # Ctrl+C, затем снова
   uv run uvicorn app.main:app --host 0.0.0.0 --port 8067 --reload
   ```

   **Docker:**
   ```bash
   docker compose restart app
   ```

## Настройка коллекций

ARMory создаёт нужные коллекции автоматически при первом обращении к соответствующему функционалу. Вручную ничего создавать не нужно.

## Лента активности

На странице проекта, во вкладке **История**, отображаются действия команды:

- новые и удалённые комментарии;
- созданные и выполненные задачи;
- созданные, отредактированные и удалённые заметки.

Каждая запись содержит автора, действие, объект и время. Frontend обновляет историю автоматически: список комментариев, задач и заметок запрашивается с параметром `since`, который равен времени последнего обновления. Polling выполняется раз в 5 секунд, поэтому изменения из другой вкладки или от другого пользователя появляются почти сразу.

> Лента активности пишется в коллекцию `project_activity` в PocketBase. Если запись не появилась, проверьте, что `POCKETBASE_ENABLED=true` и сервис PocketBase доступен.

## Продакшен без публичного доступа к админке

Если нет возможности настраивать DNS и OIDC для отдельного субдомена, PocketBase можно оставить доступным только внутри Docker-сети. ARMory будет обращаться к нему по `http://pocketbase:8090`, а пользователи будут работать через интерфейс ARMory (вкладки Задачи, Заметки, Обсуждение).

### Переменные окружения

```env
POCKETBASE_ENABLED=true
POCKETBASE_URL=http://pocketbase:8090
POCKETBASE_PUBLIC_URL=http://pocketbase:8090
POCKETBASE_ADMIN_EMAIL=admin@example.com
POCKETBASE_ADMIN_PASSWORD=changeme
```

### Запуск

```bash
docker compose up -d --build
```

При такой настройке ссылка **PocketBase** в меню ARMory не отображается, потому что админка не доступна из браузера.

### Доступ к админке через SSH-туннель

Если нужно зайти в админку PocketBase на сервере:

```bash
ssh -L 8090:localhost:8090 user@твой-сервер
```

После этого открываешь в браузере:

```text
http://localhost:8090/_/
```

## Продакшен с отдельным субдоменом

Рекомендуемая схема — выделить PocketBase на собственный субдомен с отдельным шлюзом авторизации, например `https://pocketbase.armory.team-73.ru`.

### Требования

- Свободный порт на сервере для шлюза PocketBase (по умолчанию `5006`, задаётся в `.env` через `POCKETBASE_GATEWAY_PORT`).
- DNS-запись `pocketbase.armory.team-73.ru` → IP сервера.
- Внешний reverse proxy (например, Nginx или Traefik), который принимает `https://pocketbase.armory.team-73.ru` и проксирует на `http://127.0.0.1:POCKETBASE_GATEWAY_PORT`.
- Настроенный OIDC-клиент для нового шлюза (тот же Stalwart / mail.team-73.ru, но отдельный `client_id/client_secret`).

### Переменные окружения

```env
POCKETBASE_ENABLED=true
POCKETBASE_URL=http://pocketbase:8090
POCKETBASE_PUBLIC_URL=https://pocketbase.armory.team-73.ru
POCKETBASE_ADMIN_EMAIL=admin@example.com
POCKETBASE_ADMIN_PASSWORD=changeme
POCKETBASE_GATEWAY_PORT=5006

# Отдельный OIDC-клиент для шлюза PocketBase
OAUTH2_PROXY_CLIENT_ID=pocketbase
OAUTH2_PROXY_CLIENT_SECRET=<client_secret>
```

### Запуск

```bash
docker compose -f compose.yml -f compose.pocketbase-gateway.yml up -d
```

При каждом запуске контейнера `pocketbase` администратор автоматически создаётся или обновляется по `POCKETBASE_ADMIN_EMAIL`/`POCKETBASE_ADMIN_PASSWORD`, поэтому ручной шаг `superuser create` не нужен.

### Пример правила для внешнего Nginx

```nginx
server {
    listen 443 ssl http2;
    server_name pocketbase.armory.team-73.ru;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:5006;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Бэкап

Все данные PocketBase хранятся на хосте в папке `./data/pb_data`, миграции схемы — в `./data/pb_migrations`. В контейнере это смонтировано в `/pb/pb_data` и `/pb/pb_migrations`.

Быстрый бэкап через скрипт:

```bash
./scripts/backup_pocketbase.sh
```

По умолчанию архив сохраняется в `data/backups/pb_data_YYYYMMDD_HHMMSS.tar.gz`. Можно передать другую папку:

```bash
./scripts/backup_pocketbase.sh /mnt/backups
```

Ручной бэкап:

```bash
tar czf ./data/backups/pocketbase_$(date +%Y%m%d_%H%M%S).tar.gz -C ./data pb_data pb_migrations
```

Восстановить из архива (ARMory и PocketBase должны быть остановлены):

```bash
docker compose down
rm -rf ./data/pb_data ./data/pb_migrations
tar xzf ./data/backups/pocketbase_YYYYMMDD_HHMMSS.tar.gz -C ./data
docker compose up -d
```

> Регулярно бэкапьте папки `data/pb_data` и `data/pb_migrations`. Для автоматизации добавьте `./scripts/backup_pocketbase.sh` в cron или планировщик ARMory.

## Автозагрузка (systemd)

Чтобы PocketBase поднимался автоматически при старте системы (как у тебя ARMory через `armory-app.service`), используй systemd unit:

```bash
sudo cp scripts/armory-pocketbase.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now armory-pocketbase.service
```

Проверить статус:

```bash
sudo systemctl status armory-pocketbase.service
```

Unit запускает `./scripts/run_pocketbase.sh` из рабочей папки `/home/zerocreator/ARMory/`, перезапускается при падении и стартует после поднятия сети.

## Безопасность

- Admin-токен хранится только в `.env` и используется на сервере ARMory.
- Frontend не обращается к PocketBase напрямую — только через API ARMory.
- Админ-панель PocketBase `/_/` не должна быть открыта публично без дополнительной защиты (oauth2-proxy решает эту задачу).
