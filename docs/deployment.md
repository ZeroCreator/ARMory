# Деплой на production

## Быстрый старт

```bash
# 1. Клонируй репозиторий
git clone <repo-url> <project-directory>
cd <project-directory>

# 2. Создай .env
cp .env.example .env
nano .env
```

В `.env` укажи:
```env
DATABASE_URL="sqlite+aiosqlite:///./data/armory.db"
LOCAL_STORAGE_PATH=./data/uploads
STORAGE_TYPE=local
ARMORY_PUBLIC_URL=https://<your-domain>

# Yandex Disk (опционально)
YANDEX_DISK_TOKEN=your_oauth_token
YANDEX_DISK_PATH=ARMory/data
YANDEX_DISK_BACKUPS_PATH=ARMory/backups
YANDEX_DISK_ALEXANDRITE_PATH=ARMory/alexandrite
TIMEZONE=Europe/Moscow

# Alexandrite
ALEXANDRITE_VAULT_PATH=./data/alexandrite
ALEXANDRITE_YANDEX_ROOT_PATH=ARMory

# Планировщик: проекты со скриптами и ssh-доступ к их серверам
SCRIPTS_PROJECT_PATHS=<project-a-directory>,<project-b-directory>
SCRIPTS_PROJECT_SSH=project-a=<ssh-user>@<server-a>,project-b=<ssh-user>@<server-b>
SCHEDULER_SSH_KEY=<container-ssh-key-path>
SCHEDULER_SSH_KEY_HOST=<host-ssh-key-path>

```

```bash
# 3. Создай папку для данных
mkdir -p data/uploads

# 4. Если переносишь данные с другой машины — распакуй бэкап:
# tar -xzvf backup_20260520.tar.gz
# mv armory.db data/
# mv uploads/* data/uploads/

# 5. Запуск
docker compose up -d --build
```

Приложение доступно на `http://<server-host>:<port>`.

## Запуск с auth gateway (oauth2-proxy)

Если нужно закрыть ARMory авторизацией через внешний OIDC-провайдер:

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

Callback URL для OIDC-провайдера: `https://<your-domain>/oauth2/callback`.

## Collabora Online

Для редактирования офисных документов в Alexandrite добавьте в `.env`:

```env
COLLABORA_ENABLED=true
COLLABORA_DOMAIN=<your-domain>
COLLABORA_INTERNAL_URL=http://<collabora-service>:<collabora-port>
COLLABORA_PUBLIC_URL=https://<your-domain>/collabora
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
        proxy_pass http://<armory-host>:<armory-port>;
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
cd <project-directory>
git pull

# Бэкап перед обновлением
tar -czvf backup_$(date +%Y%m%d_%H%M%S).tar.gz data/ armory.db

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

## Подключаемые приложения

В Compose страница **Приложения → Управление** передаёт операции внутреннему сервису `extension-manager`. Только он монтирует Docker socket; основной ARMory не получает прямого доступа к Docker Engine. Не публикуйте порт менеджера и обязательно ограничьте страницу административной аутентификацией gateway. При запуске ARMory без Docker используется локальный Docker CLI текущего пользователя. Подробности: [Подключаемые приложения](applications.md).

## Проверка статуса

```bash
docker compose ps
curl -s http://<armory-host>:<armory-port>/api/projects
```
