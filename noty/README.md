# Noty — структура проекта

Проект приведён к целевой модульной структуре:
- `core/` — orchestration, роутинг, контекст, API-ротация.
- `filters/` — эвристика + embedding-фильтрация.
- `memory/` — SQLite + Mem0 + отношения.
- `prompts/` — слои промптов и версии personality.
- `tools/` — безопасные инструменты и executor.
- `mood/`, `thought/` — состояние, энергия, внутренний монолог.
- `config/`, `data/`, `utils/` — окружение, хранение, утилиты.

Источник требований: `../noty_specification.md`.


## Внешняя настройка промптов и характера
- JSON-конфиг: `config/persona_prompt_config.json` (маркеры, persona adaptation policy, fallback-стиль).
- CLI-терминал: `python -m noty.tools.persona_terminal`.
  - `show` — показать текущий конфиг.
  - `set <dotted.key> <value>` — изменить значение в конфиге.
  - `edit-prompt base_core.txt "..."` — быстро заменить базовый prompt-слой.
