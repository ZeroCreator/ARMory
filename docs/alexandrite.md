# Alexandrite

**Alexandrite** — файловое хранилище заметок в стиле Obsidian. Позволяет подключить любую папку на диске (например, vault Obsidian) и работать с её содержимым прямо в ARMory.

## Возможности

- Подключение любой локальной папки через UI.
- Древовидная структура файлов и папок в левом сайдбаре.
- Hover-просмотр файлов в правой панели.
- Поддержка текстовых файлов (Markdown, код, plain text) и изображений.
- Создание файлов `.md` и `.txt`.
- Создание вложенных папок.
- Контекстное меню по правому клику:
  - **Для папок**: добавить файл, добавить подпапку, переименовать, удалить.
  - **Для файлов**: переименовать, удалить.
- Редактирование Markdown и текстовых файлов с предпросмотром.

## Настройка

По умолчанию используется папка `./data/uploads` (относительно рабочей директории ARMory). Её можно переопределить через переменную окружения:

```bash
ALEXANDRITE_VAULT_PATH=/home/user/alexandrite
```

В UI также можно выбрать другую папку на лету.

## API

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/alexandrite/roots` | Настроенные корневые папки |
| GET | `/api/alexandrite/tree?root=<path>` | Дерево файлов и папок |
| GET | `/api/alexandrite/file?root=<path>&path=<relative>` | Содержимое файла |
| POST | `/api/alexandrite/file?root=<path>` | Создать файл `.md` или `.txt` |
| PUT | `/api/alexandrite/file?root=<path>` | Обновить содержимое файла |
| PATCH | `/api/alexandrite/file?root=<path>` | Переименовать файл |
| DELETE | `/api/alexandrite/file?root=<path>&path=<relative>` | Удалить файл |
| POST | `/api/alexandrite/directory?root=<path>` | Создать папку |
| PATCH | `/api/alexandrite/directory?root=<path>` | Переименовать папку |
| DELETE | `/api/alexandrite/directory?root=<path>&path=<relative>` | Удалить папку со всем содержимым |
