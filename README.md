# noti-agent

Репозиторий приведён к модульной структуре `noty/` согласно `noty_specification.md`.

## Quick Start (без Docker)
1. Подготовить окружение (Windows/Linux):
   - Windows (PowerShell):
     ```powershell
     ./scripts/setup.ps1
     ```
   - Linux/macOS:
     ```bash
     ./scripts/setup.sh
     ```
   - или напрямую:
     ```bash
     python -m noty.cli setup
     ```
2. При необходимости заполнить `noty/config/.env`, `noty/config/bot_config.yaml` и `noty/config/api_keys.json`.
3. Запустить локально:
   ```bash
   python -m noty.cli run
   ```
4. Открыть web-панель настройки (localhost):
   ```bash
   python -m noty.cli panel --host 127.0.0.1 --port 8765
   ```
   Логин: `admin`, пароль берётся из `LOCAL_PANEL_PASSWORD` в `noty/config/.env`.

> Telegram не обязателен для first-run профиля: по умолчанию активна только платформа VK.

## Структура
См. `noty/README.md` и `TASK_MAP.md`.

## Интеграции LLM/памяти
- `LiteLLM` поддержан как альтернативный backend (`llm.backend` в `noty/config/bot_config.yaml`).
- `Instructor` подключён для structured outputs в `APIRotator.structured_call`.
- `LlamaIndex` добавлен как опциональный семантический ретривер для расширения контекста.
