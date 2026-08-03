# Локальная модель для работы с ARMory

ARMory не зависит от конкретного поставщика модели. Любую локальную модель, запущенную через OpenAI-совместимый сервер, можно использовать с MCP-клиентом (Claude Code, Cline, Continue, mcpm-aider и др.), который подключается к endpoint `/mcp` ARMory.

Ниже — пример запуска локальной модели Qwen через `llama.cpp` и варианты подключения MCP-клиентов.

## Требования

- Python-окружение ARMory настроено (`.venv`).
- Установлен `llama.cpp` с сервером.
- Видеокарта и RAM достаточны для выбранной модели.

Пример конфигурации машины:

- RTX 5060 с 8 ГБ VRAM;
- 32 GB RAM;
- модель `Qwen2.5-Coder-14B Q4_K_M` (~9 ГБ файла);
- контекст `-c 8192`.

## 1. Запуск локальной модели

Перейди в папку `llama.cpp` и запусти сервер:

```bash
cd ~/llama.cpp

./build/bin/llama-server \
  -hf Qwen/Qwen2.5-Coder-14B-Instruct-GGUF:Q4_K_M \
  --host 127.0.0.1 \
  --port 8082 \
  -ngl 25 \
  -c 8192 \
  --flash-attn on
```

### Проверить, что модель запущена

```bash
pgrep -af llama-server
# или
ps -ef | grep llama-server
```

### Проверить API

```bash
curl http://127.0.0.1:8082/v1/models
```

### Логи

```bash
tail -100 ~/llama-server.log
```

### Остановить сервер

```bash
pkill -f llama-server
```

## 2. Настройка MCP-клиента

Локальная модель сама по себе не является MCP-клиентом. Нужен клиент, который:

1. Умеет общаться с локальной моделью по OpenAI-совместимому API.
2. Поддерживает MCP и умеет подключаться к `/mcp` ARMory.

### Вариант A: Claude Code / Cline / Continue

Эти инструменты позволяют указать собственный OpenAI-совместимый endpoint и список MCP-серверов.

Настройки модели:

- Base URL: `http://localhost:8082/v1`
- Model: `Qwen/Qwen2.5-Coder-14B-Instruct-GGUF:Q4_K_M`
- API key: `local` (или любая строка, если сервер не проверяет ключ)

Настройки MCP-сервера ARMory:

```json
{
  "mcpServers": {
    "armory": {
      "url": "http://localhost:5005/mcp",
      "headers": {
        "X-MCP-API-Key": "YOUR_MCP_API_KEY"
      }
    }
  }
}
```

Укажи порт ARMory, на котором запущен backend (обычно `5005` в Docker или `8000` при локальном `uvicorn`).

### Вариант B: Aider + локальная модель

Aider напрямую не поддерживает MCP, но может работать с локальной моделью в качестве coding-ассистента. ARMory при этом используется через веб-интерфейс для управления задачами, а Aider — для редактирования кода.

```bash
aider \
  --model openai/Qwen/Qwen2.5-Coder-14B-Instruct-GGUF:Q4_K_M \
  --openai-api-base http://localhost:8082/v1 \
  --openai-api-key local \
  --chat-language Russian \
  --map-tokens 4096
```

### Вариант C: mcpm-aider

Существуют сторонние обёртки (`mcpm-aider`), которые добавляют Aider поддержку MCP. В таком случае Aider выступает MCP-клиентом, а ARMory — MCP-сервером. Конфигурация зависит от конкретной обёртки, но обычно сводится к указанию:

- URL модели: `http://localhost:8082/v1`
- MCP-сервера ARMory: `http://localhost:5005/mcp`
- API-ключа `MCP_API_KEY`

## 3. Настройка .env в ARMory

Добавь в `.env` параметры локальной модели (используются MCP-клиентами и документацией):

```env
# AI-ассистент, от имени которого MCP берёт/назначает задачи
AI_ASSIGNEE_EMAIL=ai@armory.local
AI_ASSIGNEE_NAME=AI Assistant

# Локальная LLM (OpenAI-совместимый API)
LOCAL_LLM_BASE_URL=http://localhost:8082/v1
LOCAL_LLM_MODEL=Qwen/Qwen2.5-Coder-14B-Instruct-GGUF:Q4_K_M
LOCAL_LLM_API_KEY=local
```

## 4. Проверка работы

1. Запусти `llama-server`.
2. Запусти ARMory backend.
3. Открой MCP-клиент, настроенный на локальную модель и MCP ARMory.
4. Попробуй команду:

```
Покажи задачу #39
```

Ассистент должен вызвать `mcp__armory__get_task` и вернуть данные задачи.

## Другие серверы локальных моделей

Вместо `llama.cpp` можно использовать любой OpenAI-совместимый сервер:

- **Ollama** — `ollama run qwen2.5-coder:14b`, endpoint `http://localhost:11434/v1`.
- **vLLM** — `vllm serve ...`, endpoint `http://localhost:8000/v1`.
- **llamafile** — портативный бинарник.

Главное — чтобы сервер отвечал на `/v1/models` и `/v1/chat/completions` в формате OpenAI.

## Ссылки

- [llama.cpp server](https://github.com/ggerganov/llama.cpp/blob/master/examples/server/README.md)
- [Ollama OpenAI compatibility](https://github.com/ollama/ollama/blob/main/docs/openai.md)
- [MCP specification](https://modelcontextprotocol.io/specification/latest)
