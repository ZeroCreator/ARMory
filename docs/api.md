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
| DELETE | `/api/projects/{id}/sections/{sec_id}` | Удалить раздел вместе со всеми группами, элементами и файлами |

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
| GET | `/api/projects/{id}/documents/{doc_id}/items/{item_id}/collabora` | URL iframe для редактирования в Collabora Online |
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

## Глоссарий

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/glossary` | Список терминов (пагинация, поиск, фильтр по теме/подтеме) |
| GET | `/api/glossary/count` | Количество терминов с учётом фильтров |
| POST | `/api/glossary` | Создать термин |
| GET | `/api/glossary/{id}` | Получить термин |
| PATCH | `/api/glossary/{id}` | Обновить термин |
| DELETE | `/api/glossary/{id}` | Удалить термин |
| GET | `/api/glossary/topics` | Список тем с подтемами |
| POST | `/api/glossary/topics` | Создать тему |
| PATCH | `/api/glossary/topics/{id}` | Обновить тему |
| DELETE | `/api/glossary/topics/{id}` | Удалить тему |
| GET | `/api/glossary/subtopics` | Список подтем |
| POST | `/api/glossary/subtopics` | Создать подтему |
| PATCH | `/api/glossary/subtopics/{id}` | Обновить подтему |
| DELETE | `/api/glossary/subtopics/{id}` | Удалить подтему |
| GET | `/api/glossary/export` | Экспорт глоссария в `.xlsx` |
| POST | `/api/glossary/import` | Импорт глоссария из `.xlsx` |

## Alexandrite

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/alexandrite/roots` | Настроенные корневые папки |
| GET | `/api/alexandrite/tree?root=<path>` | Дерево файлов и папок |
| GET | `/api/alexandrite/file?root=<path>&path=<relative>` | Содержимое файла |
| POST | `/api/alexandrite/file?root=<path>` | Создать файл `.md`/`.txt` |
| PUT | `/api/alexandrite/file?root=<path>` | Обновить содержимое файла |
| PATCH | `/api/alexandrite/file?root=<path>` | Переименовать файл |
| DELETE | `/api/alexandrite/file?root=<path>&path=<relative>` | Удалить файл |
| POST | `/api/alexandrite/directory?root=<path>` | Создать папку |
| PATCH | `/api/alexandrite/directory?root=<path>` | Переименовать папку |
| DELETE | `/api/alexandrite/directory?root=<path>&path=<relative>` | Удалить папку рекурсивно |

## Бэкапы и синхронизация (Яндекс.Диск)

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/backup/stats` | Статистика локальных данных и статус Яндекс.Диска |
| POST | `/api/backup/sync-export` | Синхронизация на Яндекс.Диск (DB + uploads); возвращает `job_id` |
| POST | `/api/backup/sync-import` | Синхронизация с Яндекс.Диска (DB + uploads) |
| GET | `/api/backup/job/{job_id}` | Статус фоновой задачи синхронизации или архива |
| GET | `/api/backup/archives` | Список архивных бэкапов на Яндекс.Диске |
| POST | `/api/backup/create` | Создать архив `.tar.gz` и загрузить на Яндекс.Диск; возвращает `job_id` |
| POST | `/api/backup/restore` | Восстановить данные из архива на Яндекс.Диске |
| POST | `/api/backup/delete` | Удалить архив с Яндекс.Диска |
| GET | `/api/backup/alexandrite/stats` | Статистика локальной папки Alexandrite |
| POST | `/api/backup/alexandrite/export` | Синхронная загрузка Alexandrite на Яндекс.Диск |
| POST | `/api/backup/alexandrite/export-async` | Асинхронная загрузка Alexandrite; возвращает `job_id` |
| GET | `/api/backup/alexandrite/export-status/{job_id}` | Статус фоновой загрузки Alexandrite |
| POST | `/api/backup/alexandrite/import` | Загрузить Alexandrite с Яндекс.Диска |
| POST | `/api/backup/alexandrite/archive` | Создать архив Alexandrite на Яндекс.Диске |
| GET | `/api/backup/alexandrite/archives` | Список архивов Alexandrite |
| POST | `/api/backup/alexandrite/restore` | Восстановить Alexandrite из архива |
