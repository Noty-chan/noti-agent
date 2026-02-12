# noti-agent

Репозиторий приведён к модульной структуре `noty/` согласно `noty_specification.md`.

## Быстрый старт
1. Заполнить `noty/config/.env` и `noty/config/api_keys.json`.
2. Установить зависимости:
   ```bash
   pip install -r requirements.txt
   ```
3. Запустить:
   ```bash
   python main.py
   ```

## Структура
См. `noty/README.md` и `TASK_MAP.md`.

## Интеграции LLM/памяти
- `LiteLLM` поддержан как альтернативный backend (`llm.backend` в `noty/config/bot_config.yaml`).
- `Instructor` подключён для structured outputs в `APIRotator.structured_call`.
- `LlamaIndex` добавлен как опциональный семантический ретривер для расширения контекста.
