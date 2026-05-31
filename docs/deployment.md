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
APP_NAME="Your App Name"
DATABASE_URL="sqlite+aiosqlite:///./data/projectdocs.db"
LOCAL_STORAGE_PATH=./data/uploads
STORAGE_TYPE=local
```

```bash
# 3. Создай папку для данных
mkdir -p data/uploads

# 4. Если переносишь данные с другой машины — распакуй бэкап:
# tar -xzvf backup_20260520.tar.gz
# mv projectdocs.db data/
# mv uploads/* data/uploads/

# 5. Запуск
docker compose up -d --build
```

Приложение доступно на `http://server-ip:<PORT>` (порт по умолчанию смотрите в `docker-compose.yml`).

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
tar -czvf backup_$(date +%Y%m%d_%H%M%S).tar.gz data/

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
