# Деплой на production

## Быстрый старт

```bash
# 1. Клонируй репозиторий
git clone <repo-url> /opt/<your-project>
cd /opt/<your-project>

# 2. Создай .env
cp .env.example .env
nano .env
```

В `.env` укажи:
```env
DATABASE_URL="sqlite+aiosqlite:///./data/projectdocs.db"
LOCAL_STORAGE_PATH=./data/uploads
STORAGE_TYPE=local
ARMORY_PUBLIC_URL=https://armory.team-73.ru

# Yandex Disk (опционально)
YANDEX_DISK_TOKEN=your_oauth_token
YANDEX_DISK_PATH=ARMory/data
YANDEX_DISK_BACKUPS_PATH=ARMory/backups
YANDEX_DISK_ALEXANDRITE_PATH=ARMory/alexandrite
TIMEZONE=Europe/Moscow

# Alexandrite
ALEXANDRITE_VAULT_PATH=./data/alexandrite
ALEXANDRITE_YANDEX_ROOT_PATH=ARMory

# Планировщик
SCHEDULER_ENABLED=true

# PocketBase
POCKETBASE_PROJECTS=intraservice,armory
POCKETBASE_DEFAULT_PROJECT=intraservice
POCKETBASE_BASE_PORT=8091
POCKETBASE_ADMIN_EMAIL=admin@example.com
POCKETBASE_ADMIN_PASSWORD=<сложный пароль>
```

```bash
# 3. Создай папку для данных
mkdir -p data/uploads

# 4. Если переносишь данные с другой машины — распакуй бэкап:
# tar -xzvf backup_20260520.tar.gz
# mv projectdocs.db data/
# mv uploads/* data/uploads/

# 5. Если используется PocketBase — скопируй данные проектов:
# rsync -av source/data/pb_data/ data/pb_data/
# rsync -av source/data/pb_migrations/ data/pb_migrations/

# 6. Запуск
docker compose up -d --build
```

Приложение доступно на `http://server-ip:<PORT>` (порт по умолчанию смотрите в `compose.yml`).

## Запуск с auth gateway (oauth2-proxy)

Если нужно закрыть ARMory авторизацией через Stalwart (mail.team-73.ru):

```bash
docker compose -f compose.yml -f compose.gateway.yml up -d
```

В `.env` заполни:
```env
GATEWAY_PORT=5005
OAUTH2_PROXY_CLIENT_ID=armory
OAUTH2_PROXY_CLIENT_SECRET=<secret от админа Stalwart>
OAUTH2_PROXY_COOKIE_SECRET=<openssl rand -base64 32>
```

Callback URL для Stalwart: `https://armory.team-73.ru/oauth2/callback`.

## Collabora Online

Для редактирования офисных документов в Alexandrite добавьте в `.env`:

```env
COLLABORA_ENABLED=true
COLLABORA_DOMAIN=armory.team-73.ru
COLLABORA_INTERNAL_URL=http://collabora:9980
COLLABORA_PUBLIC_URL=https://armory.team-73.ru/collabora
COLLABORA_SERVICE_ROOT=/collabora
COLLABORA_WOPI_SECRET=<openssl rand -hex 32>
COLLABORA_ADMIN_USER=admin
COLLABORA_ADMIN_PASSWORD=<сложный пароль>
```

Запустите стек с Collabora:

```bash
docker compose -f compose.yml -f compose.gateway.yml up -d --build
```

ARMory автоматически проксирует `/collabora/*` на внутренний сервис Collabora, поэтому дополнительная настройка шлюза не требуется.

## HTTPS + домен (Nginx + Certbot)

```bash
sudo apt update && sudo apt install nginx certbot python3-certbot-nginx -y

sudo tee /etc/nginx/sites-available/<your-app> << 'EOF'
server {
    listen 80;
    server_name <your-domain>;

    location / {
        proxy_pass http://127.0.0.1:<PORT>;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/<your-app> /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx

# SSL
sudo certbot --nginx -d <your-domain>
```

## Обновление кода

```bash
cd /opt/<your-project>
git pull

# Бэкап перед обновлением
tar -czvf backup_$(date +%Y%m%d_%H%M%S).tar.gz data/ projectdocs.db

# Пересобрать и перезапустить
docker compose up -d --build
```

## Проверка логов

```bash
# Логи приложения
docker compose logs -f

# Или напрямую
docker logs -f <container-name>
```

## Проверка статуса

```bash
docker compose ps
curl -s http://localhost:<PORT>/api/projects
```
