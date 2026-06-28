# Alexandrite

**Alexandrite** — файловое хранилище заметок в стиле Obsidian. Позволяет работать с заметками локально или просматривать папку на Яндекс.Диске прямо в ARMory.

## Возможности

- Подключение любой локальной папки через UI.
- **Просмотр Яндекс.Диска** — переключатель «Локально» / «Яндекс.Диск» в шапке Alexandrite.
  - В режиме Яндекс.Диска дерево загружается по уровням.
  - Поддерживается просмотр текстовых файлов и изображений.
  - Редактирование, создание и удаление файлов/папок в режиме Яндекс.Диска недоступны.
- Древовидная структура файлов и папок в левом сайдбаре.
- Hover-просмотр файлов в правой панели.
- Поддержка текстовых файлов (Markdown, код, plain text) и изображений.
- **Бинарные файлы** (`.docx`, `.xlsx`, `.pdf` и др.): предпросмотр не отображается, но по клику файл открывается в системном приложении при локальном запуске ARMory. При удалённом доступе файл скачивается.
- **Светлый режим дня** — переключатель в правом верхнем углу панели предпросмотра перекрашивает сайдбар и область просмотра в светло-песочную тему. Выбор сохраняется в localStorage.
- **Collabora Online** — редактирование офисных файлов (`.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`) прямо в браузере. Клик по файлу открывает редактор в области предпросмотра.
- Создание файлов `.md` и `.txt`.
- Создание вложенных папок.
- Контекстное меню по правому клику:
  - **Для папок**: добавить файл, добавить подпапку, переименовать, удалить.
  - **Для файлов**: переименовать, удалить.
- Редактирование Markdown и текстовых файлов с предпросмотром.

## Настройка

По умолчанию используется папка `./data/alexandrite` (относительно рабочей директории ARMory). Её можно переопределить через переменную окружения:

```bash
ALEXANDRITE_VAULT_PATH=/home/user/alexandrite
```

В UI также можно выбрать другую локальную папку на лету.

### Ограничение просмотра Яндекс.Диска

Чтобы в режиме Яндекс.Диска видеть не весь диск, а только определённую папку (например, `ARMory`):

```env
ALEXANDRITE_YANDEX_ROOT_PATH=ARMory
```

Если переменная не задана или пустая — доступен весь Яндекс.Диск.

### Collabora Online

Для редактирования офисных документов в браузере включите Collabora Online в `.env`:

```env
COLLABORA_ENABLED=true
COLLABORA_DOMAIN=armory.team-73.ru
COLLABORA_INTERNAL_URL=http://collabora:9980
COLLABORA_PUBLIC_URL=https://armory.team-73.ru/collabora
COLLABORA_SERVICE_ROOT=/collabora
COLLABORA_WOPI_SECRET=<сгенерируйте через openssl rand -hex 32>
COLLABORA_ADMIN_USER=admin
COLLABORA_ADMIN_PASSWORD=<сложный пароль>
```

Collabora запускается как отдельный сервис в `compose.yml`. ARMory проксирует запросы по пути `/collabora/*` и предоставляет WOPI endpoints по пути `/wopi/*` для загрузки и сохранения файлов.

Поддерживаемые форматы: `.docx`, `.doc`, `.xlsx`, `.xls`, `.pptx`, `.ppt`, `.odt`, `.ods`, `.odp`.

## API

### Локальное хранилище

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/alexandrite/roots` | Настроенные корневые папки |
| GET | `/api/alexandrite/tree?root=<path>` | Дерево файлов и папок |
| GET | `/api/alexandrite/file?root=<path>&path=<relative>` | Содержимое файла |
| GET | `/api/alexandrite/file/download?root=<path>&path=<relative>` | Скачать файл |
| POST | `/api/alexandrite/file/open?root=<path>&path=<relative>` | Открыть файл в системном приложении (только `localhost`) |
| GET | `/api/alexandrite/collabora?root=<path>&path=<relative>` | URL iframe для редактирования в Collabora Online |
| POST | `/api/alexandrite/file?root=<path>` | Создать файл `.md` или `.txt` |
| PUT | `/api/alexandrite/file?root=<path>` | Обновить содержимое файла |
| PATCH | `/api/alexandrite/file?root=<path>` | Переименовать файл |
| DELETE | `/api/alexandrite/file?root=<path>&path=<relative>` | Удалить файл |
| POST | `/api/alexandrite/directory?root=<path>` | Создать папку |
| PATCH | `/api/alexandrite/directory?root=<path>` | Переименовать папку |
| DELETE | `/api/alexandrite/directory?root=<path>&path=<relative>` | Удалить папку со всем содержимым |

### Яндекс.Диск (read-only)

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/alexandrite/yandex/tree?path=<path>` | Содержимое папки на Яндекс.Диске |
| GET | `/api/alexandrite/yandex/file?path=<path>` | Содержимое файла с Яндекс.Диска |
| GET | `/api/alexandrite/yandex/download?path=<path>` | Скачать файл с Яндекс.Диска |
