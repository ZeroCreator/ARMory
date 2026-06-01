# API

## Проекты

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/projects` | Список проектов |
| POST | `/api/projects` | Создать проект |
| GET | `/api/projects/{id}` | Детали проекта |
| PATCH | `/api/projects/{id}` | Обновить проект |
| DELETE | `/api/projects/{id}` | Удалить проект (+ файлы из хранилища) |

## Разделы

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/projects/{id}/sections` | Разделы проекта |
| POST | `/api/projects/{id}/sections` | Создать раздел |
| PATCH | `/api/projects/{id}/sections/reorder` | Изменить порядок разделов |
| PATCH | `/api/projects/{id}/sections/{sec_id}` | Переименовать / обновить раздел |
| DELETE | `/api/projects/{id}/sections/{sec_id}` | Удалить раздел (группы переходят в "Без раздела") |

## Документы и файлы

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/projects/{id}/documents` | Группы без раздела |
| POST | `/api/projects/{id}/documents` | Создать группу |
| PATCH | `/api/projects/{id}/documents/{doc_id}` | Обновить группу / переместить в раздел |
| DELETE | `/api/projects/{id}/documents/{doc_id}` | Удалить группу (+ файлы из хранилища) |
| POST | `/api/projects/{id}/documents/{doc_id}/items` | Добавить ссылку, файл или заметку |
| PATCH | `/api/projects/{id}/documents/{doc_id}/items/{item_id}` | Редактировать item |
| DELETE | `/api/projects/{id}/documents/{doc_id}/items/{item_id}` | Удалить item (+ файл из хранилища) |
| GET | `/api/projects/{id}/documents/{doc_id}/items/{item_id}/download` | Скачать файл |
| GET | `/api/projects/{id}/documents/{doc_id}/items/{item_id}/preview` | Предпросмотр файла |
| POST | `/api/projects/{id}/documents/{doc_id}/items/{item_id}/open` | Открыть файл в системном приложении (localhost only) |

## Сайдбар

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/sidebar/blocks` | Список блоков сайдбара |
| POST | `/api/sidebar/blocks` | Создать блок |
| PATCH | `/api/sidebar/blocks/{id}` | Обновить блок |
| DELETE | `/api/sidebar/blocks/{id}` | Удалить блок (+ ссылки) |
| POST | `/api/sidebar/blocks/{id}/links` | Добавить ссылку в блок |
| PATCH | `/api/sidebar/links/{id}` | Обновить ссылку |
| DELETE | `/api/sidebar/links/{id}` | Удалить ссылку |

## Календарь

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/calendar/events` | Список событий |
| POST | `/api/calendar/events` | Создать событие |
| PATCH | `/api/calendar/events/{id}` | Обновить событие |
| DELETE | `/api/calendar/events/{id}` | Удалить событие |

## Планировщик

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/scheduler/tasks` | Список доступных задач |
| POST | `/api/scheduler/schedule` | Запланировать задачу |
| GET | `/api/scheduler/atq` | Список запланированных задач |
| POST | `/api/scheduler/remove-task` | Удалить задачу из очереди |
