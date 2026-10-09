# Локальная модель для работы с ARMory

ARMory не зависит от конкретного поставщика модели. Любую локальную модель,
запущенную через OpenAI-совместимый сервер, можно использовать с MCP-клиентом,
который подключается к endpoint `/mcp/` ARMory.

## Требования

- настроенное Python-окружение ARMory;
- установленный сервер модели с OpenAI-совместимым API;
- ресурсы, достаточные для выбранной модели;
- MCP-клиент, который умеет работать с HTTP MCP endpoint.

Параметры видеокарты, памяти, размера модели и контекста зависят от выбранного
сервера. Проверь требования модели до запуска.

## Запуск через llama.cpp

Перейди в каталог `llama.cpp` и подставь идентификатор модели и параметры среды:

```bash
cd <llama-cpp-directory>

./build/bin/llama-server \
  -hf <model-identifier> \
  --host <model-bind-address> \
  --port <model-port> \
  -ngl <gpu-layers> \
  -c <context-tokens> \
  --flash-attn on
```

Проверь доступность сервера:

```bash
curl http://<model-host>:<model-port>/v1/models
```

Для просмотра процесса и логов используй штатные средства выбранного сервера.
После проверки запусти ARMory и убедись, что MCP-клиент видит оба endpoint.

## Настройка MCP-клиента

Локальная модель сама по себе не является MCP-клиентом. Клиент должен:

1. обращаться к модели по OpenAI-совместимому API;
2. подключаться к `/mcp/` ARMory;
3. передавать API-ключ или проходить OAuth, если это включено в ARMory.

Пример настроек модели:

- Base URL: `http://<model-host>:<model-port>/v1`;
- Model: `<model-name>`;
- API key: `<local-api-key>`.

Пример HTTP-конфигурации MCP:

```json
{
  "mcpServers": {
    "armory": {
      "url": "http://<armory-host>:<armory-port>/mcp/",
      "headers": {
        "X-MCP-API-Key": "<mcp-api-key>"
      }
    }
  }
}
```

Если используется OAuth, не добавляй API-ключ: клиент должен пройти discovery и
авторизацию через опубликованные ARMory endpoint'ы.

## Настройка локального API в ARMory

При необходимости добавь в `.env` параметры, которые используются внешними
инструментами:

```env
AI_ASSIGNEE_EMAIL=<ai-assignee-email>
AI_ASSIGNEE_NAME=<ai-assignee-name>
LOCAL_LLM_BASE_URL=http://<model-host>:<model-port>/v1
LOCAL_LLM_MODEL=<model-name>
LOCAL_LLM_API_KEY=<local-api-key>
```

## Проверка работы

1. Запусти сервер модели.
2. Запусти ARMory.
3. Подключи MCP-клиент к `/mcp/`.
4. Выполни запрос с идентификатором задачи `<task-id>` и проверь, что клиент
   использовал инструмент чтения задачи.

## Другие серверы

Подойдут Ollama, vLLM, llamafile и другие серверы, совместимые с OpenAI API.
Минимально необходимы ответы на `/v1/models` и `/v1/chat/completions`.

## Ссылки

- [llama.cpp server](https://github.com/ggerganov/llama.cpp/blob/master/examples/server/README.md)
- [Ollama OpenAI compatibility](https://github.com/ollama/ollama/blob/main/docs/openai.md)
- [MCP specification](https://modelcontextprotocol.io/specification/latest)
