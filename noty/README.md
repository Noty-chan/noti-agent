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
