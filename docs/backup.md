# Бэкапы

## Что бэкапить

Все данные хранятся в двух местах:
- `data/projectdocs.db` — база данных SQLite
- `data/uploads/` — загруженные файлы

## Ручной бэкап

```bash
cd ~/your-project
tar -czvf backup_$(date +%Y%m%d_%H%M%S).tar.gz data/projectdocs.db data/uploads/
```

Получится архив вида `backup_<timestamp>.tar.gz`.

## Восстановление из бэкапа

```bash
cd ~/your-project
tar -xzvf backup_<timestamp>.tar.gz
```

## Автоматический бэкап (cron)

```bash
# Каждый день в 3:00 утра
crontab -e
0 3 * * * cd ~/your-project && tar -czf ~/backups/app_$(date +\%Y\%m\%d).tar.gz data/projectdocs.db data/uploads/ >/dev/null 2>&1
```

## Бэкап при деплое на другой сервер

```bash
# На исходной машине
tar -czvf backup_$(date +%Y%m%d_%H%M%S).tar.gz data/projectdocs.db data/uploads/ .env

# На новом сервере
mkdir -p /opt/your-project && cd /opt/your-project
tar -xzvf backup_<timestamp>.tar.gz
# Запуск
docker compose up -d --build
```
