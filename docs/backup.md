# Бэкапы и синхронизация

Все данные ARMory хранятся в двух местах:
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

## Синхронизация с Яндекс.Диском

В интерфейсе на вкладке **«Синхронизация»** доступны операции. Блоки «Статистика», «Синхронизация с Яндекс.Диском» и «Alexandrite» можно сворачивать / разворачивать; состояние сохраняется в браузере.

### Статистика

Карточки с информацией о локальных данных (проекты, разделы, группы, файлы, заметки и т.д.) и статусе подключения к Яндекс.Диску.

### Синхронизация с Яндекс.Диском

#### Сохранить на Яндекс.Диск
Загружает `projectdocs.db` и все файлы из `data/uploads/` на Яндекс.Диск в папку `YANDEX_DISK_PATH` (по умолчанию `ARMory/data/`). Файлы, уже имеющиеся на диске, пропускаются.

#### Загрузить с Яндекс.Диска
Скачивает `projectdocs.db` и папку `uploads/` с Яндекс.Диска и восстанавливает локально. Перед операцией автоматически создаётся локальная резервная копия в `data/backups/auto_<timestamp>/`.

### Архивные бэкапы ARMory

Отдельный функционал для создания снапшотов в виде `.tar.gz`:

- **Создать архив** — упаковывает `projectdocs.db` + `data/uploads/` в `armory_backup_<timestamp>.tar.gz` и загружает в папку `YANDEX_DISK_BACKUPS_PATH` (по умолчанию `ARMory/backups/`)
- **Восстановить** — скачивает выбранный архив и распаковывает его
- **Удалить** — удаляет архив с Яндекс.Диска

Архивы хранятся на диске и не зависят от прямой синхронизации.

### Alexandrite

Папка `ALEXANDRITE_VAULT_PATH` (по умолчанию `data/alexandrite`) синхронизируется с Яндекс.Диском отдельно от основных данных ARMory:

- **Сохранить на Яндекс.Диск** — фоновая загрузка папки Alexandrite с отображением прогресса.
- **Загрузить с Яндекс.Диска** — замена локальной папки Alexandrite версией с диска. Перед операцией создаётся локальная резервная копия.
- **Архивные бэкапы** — создание архива `alexandrite_backup_<timestamp>.tar.gz` только с содержимым папки Alexandrite, восстановление и удаление архивов.

## Настройка

Добавьте в `.env`:

```env
YANDEX_DISK_TOKEN=your_oauth_token
YANDEX_DISK_PATH=ARMory/data
YANDEX_DISK_BACKUPS_PATH=ARMory/backups
YANDEX_DISK_ALEXANDRITE_PATH=ARMory/alexandrite
TIMEZONE=Europe/Moscow
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
