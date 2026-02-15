# TASK_MAP.md — карта задач по `noty_specification.md`

## A. Архитектурный каркас (из раздела «Архитектура»)
- [x] Привести проект к модульной структуре `noty/`.
- [x] Разделить ядро на доменные модули (api/context/prompt/mood/tools/memory/thought).
- [x] Добавить transport-слой для реального VK ingestion.
- [x] Подготовить адаптер под Telegram (опциональный режим).

## B. Память и обучение (раздел «Память и обучение»)
- [x] Завести SQLite manager и таблицы из спецификации.
- [x] Добавить обёртку Mem0 (конфиг под Qdrant).
- [x] Добавить jsonl-архив мыслей и событий.
- [x] Реализовать политику TTL для кратковременного состояния.
- [x] Внедрить обновление памяти после каждого ответа (успех/провал).

## C. Фильтрация сообщений (раздел «Фильтрация сообщений»)
- [x] Реализовать эвристический фильтр (быстрый отсев).
- [x] Реализовать embedding-based фильтр.
- [x] Добавить отдельный этап рандомизации и калибровки вероятности реакции.
- [x] Собирать метрики точности фильтра и стоимости API.

## D. Характер и адаптация (раздел «Характер и адаптация»)
- [x] Реализовать модульный Prompt Builder.
- [x] Добавить версионность personality слоёв.
- [x] Реализовать MoodManager и энергию.
- [x] Добавить автоадаптацию тона по накопленной статистике и отношениям.

## E. Управление чатами / Tools (разделы «Управление чатами», «Команды на ПК»)
- [x] Реализовать безопасный `SafeToolExecutor`.
- [x] Добавить реестр tools и подтверждение опасных команд.
- [x] Добавить заготовки chat-control и pc commands.
- [x] Внедрить real-platform вызовы бан/мут/удаление сообщений.
- [x] Добавить журнал действий модерации в `data/logs/actions`.
- [x] Добавить post-processing tool execution pipeline (ResponseProcessor + tools_used/relationship/mood updates).
- [x] Стандартизировать статусы SafeToolExecutor и добавить idempotency подтверждений.

## F. Внутренний монолог (раздел «Мысленный монолог»)
- [x] Добавить генерацию внутреннего монолога отдельным вызовом.
- [x] Логировать мысли в `data/logs/thoughts/*.jsonl`.
- [x] Добавить контроль качества мыслей и их влияния на стратегию ответа.

## G. Техстек, безопасность, метрики (соответствующие разделы спецификации)
- [x] Подготовить `requirements.txt`, `docker-compose.yml`, `config/*`.
- [x] Добавить централизованный мониторинг latency / token-cost / errors.
- [x] Реализовать аудит опасных команд и откат personality-версий.
- [x] Подготовить тестовый контур (unit + smoke) для основных модулей.

## H. Фазы из плана разработки (1–10)
### Фаза 1: MVP
- [x] Подключить рабочий VK polling/webhook.
- [x] Сквозной сценарий: входящее сообщение -> ответ -> логи.

### Фаза 2: Фильтрация
- [x] Настроить пороги и долю ответа ~20%.

### Фаза 3: Память
- [x] Запоминание outcome каждого взаимодействия.

### Фаза 4: Характер и настроение
- [x] Динамическое влияние истории на стиль ответа.

### Фаза 5: Инструменты
- [x] Проверка ролей в `noty/core/response_processor.py` перед каждым `tool_call`.
  **Критерий приемки:** при недостаточной роли возвращается `denied`, executor не вызывается.
  **Тестовый артефакт:** `tests/test_tool_execution_pipeline.py` (добавить кейс `denied_by_role`).
- [x] Двухшаговое подтверждение опасных команд в `noty/tools/safe_tool_executor.py` с idempotency-ключом.
  **Критерий приемки:** первый вызов -> `confirmation_required`, повтор с тем же ключом -> ровно одно исполнение.
  **Тестовый артефакт:** `tests/test_tool_confirmation_idempotency.py`.
- [x] Привязка moderation tool calls к VK/TG адаптерам в `noty/transport/*` с единым payload.
  **Критерий приемки:** `ban_user/delete_message` возвращают `status`, `platform_action_id`, `chat_id`, `reason`.
  **Тестовый артефакт:** `tests/test_chat_control_gateways.py`.
- [x] Пост-обработка tools в `noty/core/response_processor.py` только при `success`.
  **Критерий приемки:** `mood` и `relationship` обновляются только для `success`; для `denied/failed` изменений нет.
  **Тестовый артефакт:** `tests/test_tool_execution_pipeline.py`.

### Фаза 6: Монолог
- [x] Учет мыслей в выборе стратегий и тональности.

### Фаза 7: Самомодификация
- [x] Approve/reject workflow и rollback personality.

### Фаза 8: Мультичатность
- [x] Namespace-ключи в `noty/memory/session_state.py`: `{platform}:{chat_id}:{user_id}`.
  **Критерий приемки:** состояние одного чата не читается и не изменяется из другого чата того же пользователя.
  **Тестовый артефакт:** `tests/test_multichat_isolation.py` (добавить кейс namespace state).
- [x] Изоляция динамического контекста в `noty/core/context_manager.py` по `chat_id` + `thread_id`.
  **Критерий приемки:** блоки `recent/semantic/important` не содержат сообщений из соседних чатов.
  **Тестовый артефакт:** `tests/test_multichat_isolation.py` (добавить кейс context split).
- [x] Маршрутизация в `noty/transport/router.py` с обязательным пробросом `platform/chat_id/user_id`.
  **Критерий приемки:** routing-key стабилен и одинаково доступен всем downstream-модулям pipeline.
  **Тестовый артефакт:** `tests/test_transport_event_contract.py`.
- [x] TTL-очистка в `noty/memory/session_state.py` на уровне namespace.
  **Критерий приемки:** удаляется только истекший namespace, активные соседние namespace сохраняются.
  **Тестовый артефакт:** `tests/test_session_state.py` + новый `tests/test_session_state_ttl_namespaces.py`.

### Фаза 9: Полировка
- [x] Ввести performance-бюджет в `noty/utils/metrics.py`:
  - p50 e2e latency ≤ 1200 ms,
  - p95 e2e latency ≤ 2500 ms,
  - token-cost ≤ 0.020 USD / сообщение,
  - error-rate tool-calls ≤ 2.0%.
  **Критерий приемки:** метрики публикуются по этапам `filter/context/prompt/llm/tools` с тегами платформы.
  **Тестовый артефакт:** новый `tests/test_metrics_pipeline_stages.py`.
- [x] Кэширование embedding и batching в `noty/filters/embedding_filter.py`.
  **Критерий приемки:** повторная фильтрация идентичного текста даёт cache-hit; внешних вызовов меньше на батчах.
  **Тестовый артефакт:** `tests/test_embedding_cache_batching.py`.
- [x] Адаптивный fallback провайдера в `noty/core/api_rotator.py` по latency/error.
  **Критерий приемки:** при деградации активного провайдера происходит автоматическое переключение на следующий доступный.
  **Тестовый артефакт:** `tests/test_api_rotator_adaptive_fallback.py`.
- [x] Алертинг по отклонению respond-rate от целевого коридора 20% ± 5 п.п.
  **Критерий приемки:** при отклонении создается алерт с причиной `перефильтрация` / `недофильтрация`.
  **Тестовый артефакт:** `tests/test_respond_rate_alerts.py`.

### Фаза 10: Telegram
- [x] Завершить адаптер и общий routing слой.

## Контракт мультичат-изоляции (`chat_id` scope)
- [x] `session_state`: все чтения/записи строго по ключу `{platform}:{chat_id}:{user_id}`; без fallback на “последний активный чат”.
- [x] `context_manager`: `recent/semantic/important` собираются только из того же `platform+chat_id+thread_id`.
- [x] `router`: каждое событие обязано содержать `platform`, `chat_id`, `user_id`; отсутствие любого поля = hard reject.
- [x] `response_processor/tools`: tool execution и memory updates используют текущий `chat_id` из routing context, без глобальных синглтонов.
- [x] Чекбокс готовности фазы 8: «контракт принят + `tests/test_multichat_isolation.py` и `tests/test_transport_event_contract.py` зелёные».

## Sprint-1 (2 недели)

| ID | Приоритет | Задача | Модуль(и) | Роль | Сложность | DoD |
|---|---|---|---|---|---|---|
| S1 | P1 | Ролевой gate для `tool_call` | `noty/core/response_processor.py` | Backend | M | `denied` при нехватке роли + зелёный `tests/test_tool_execution_pipeline.py` |
| S2 | P1 | Двухшаговое подтверждение `ban/mute/delete` | `noty/tools/safe_tool_executor.py` | Backend | M | `confirmation_required` -> один execute по idempotency key + зелёный `tests/test_tool_confirmation_idempotency.py` |
| S3 | P1 | Namespace-изоляция session state + TTL | `noty/memory/session_state.py` | Backend | M | нет утечек между чатами + выборочный expire namespace + зелёные `tests/test_multichat_isolation.py`, `tests/test_session_state.py` |
| S4 | P1 | Изоляция контекста по `chat_id/thread_id` | `noty/core/context_manager.py` | Backend | M | `recent/semantic/important` не смешиваются между чатами + зелёный `tests/test_multichat_isolation.py` |
| S5 | P2 | Метрики p50/p95 + token-cost по stage/platform | `noty/utils/metrics.py` | Backend/DevOps | M | есть dashboard-friendly series и smoke `tests/test_metrics_pipeline_stages.py` |
| S6 | P2 | Embedding cache + batching | `noty/filters/embedding_filter.py` | Backend | M | cache-hit ≥ 80% на повторе и снижение внешних вызовов ≥ 30% на батче + `tests/test_embedding_cache_batching.py` |
| S7 | P2 | Adaptive provider fallback | `noty/core/api_rotator.py` | Backend | S | автопереключение при SLA breach и восстановление baseline + `tests/test_api_rotator_adaptive_fallback.py` |

**Зависимости Sprint-1:** `S1 -> S2`; `S3 -> S4`; `S5` желательно до `S6/S7` для верификации эффекта «до/после».

## Матрица: задача -> тест

| Фаза / подзадача | Целевой тестовый файл (`tests/`) | Сценарий проверки | Статус |
|---|---|---|---|
| 5. Ролевой gate перед `tool_call` | `tests/test_tool_execution_pipeline.py` | Немодератор инициирует tool-call -> `denied`, executor не вызывается. | сделано |
| 5. Двухшаговое подтверждение + idempotency | `tests/test_tool_confirmation_idempotency.py` | Первый вызов -> `confirmation_required`; второй с тем же ключом -> одно выполнение. | сделано |
| 5. Привязка moderation tool calls к VK/TG | `tests/test_chat_control_gateways.py` | `ban_user/delete_message` возвращают унифицированный payload. | сделано |
| 5. Пост-обработка tools только при `success` | `tests/test_tool_execution_pipeline.py` | `mood/relationship` меняются только при `success`. | сделано |
| 8. Namespace-изоляция state | `tests/test_multichat_isolation.py` | Нет утечек state между чатами одного пользователя. | сделано |
| 8. Изоляция динамического контекста | `tests/test_multichat_isolation.py` | `recent/semantic/important` не содержат чужие сообщения. | сделано |
| 8. Contract routing-key и поля события | `tests/test_transport_event_contract.py` | `platform/chat_id/user_id` обязательны, routing-key стабилен. | сделано |
| 8. TTL на уровне namespace | `tests/test_session_state.py`, `tests/test_session_state_ttl_namespaces.py` | Истекает только целевой namespace. | сделано |
| 9. Метрики p50/p95 + token-cost по stage | `tests/test_metrics_pipeline_stages.py` | Метрики экспортируются по этапам и платформам. | сделано |
| 9. Embedding cache + batching | `tests/test_embedding_cache_batching.py` | cache-hit на повторе, меньше внешних вызовов в батче. | сделано |
| 9. Adaptive provider fallback | `tests/test_api_rotator_adaptive_fallback.py` | Автопереключение при деградации latency/error. | сделано |
| 9. Respond-rate alerts | `tests/test_respond_rate_alerts.py` | Алерт за пределами 20% ± 5 п.п. с причиной. | сделано |

---

## I. Текущая итерация (интеграции и поведение)
- [x] Добавить опциональный backend `litellm` в `APIRotator` для унифицированных вызовов LLM.
- [x] Добавить `structured_call` через Instructor для типизированных ответов.
- [x] Подключить LlamaIndex-ретривер в Dynamic Context Builder как расширение семантического слоя.
- [x] Сохранить цельную память между чатами с учетом chat-scope в промпте (global memory + atmosphere).
- [x] Добавить право Ноти игнорировать неинтересные личные чаты по relationship score.
- [x] Усилить логирование в основных модулях (`api_rotator`, `context_manager`, `bot`).

## Приоритет следующего итерационного цикла
1. Реальный VK ingestion + сквозной MVP.
2. Метрики фильтрации и стоимости.
3. Автообновление памяти/отношений после ответа.
4. Тестовый контур.

## J. Persona-профиль и внешняя настройка промптов
- [x] Добавить модель `UserPersonaProfile` и хранение в SQLite по user/chat.
- [x] Обновлять persona-профиль из диалоговых сигналов (эвристика + LLM extraction с confidence validation).
- [x] Передавать persona-срез в Dynamic Context Builder и Prompt Construction.
- [x] Добавить post-check ответа по persona-ограничениям и fallback на консервативный стиль.
- [x] Логировать persona-метрики (`style_match_score`, `sarcasm_intensity`, `persona_confidence`).
- [x] Вынести prompt-настройки в внешний конфиг и добавить CLI-терминал редактирования.

- [x] Добавить распознавание прозвищ/алиасов пользователей, валидацию и хранение связей в памяти.

## K. Bugfix-итерация (стабилизация transport)
- [x] Исправить обработку Telegram `id=0/update_id=0` без ложного fallback на `unknown`.
- [x] Улучшить локальный CLI web-панели: явная ошибка при занятом порту и `--reload` для dev-режима.


## L. План внедрения «лёгкий локальный запуск + web-настройка + новая память»

> Формат: 4 последовательные задачи. Каждая следующая опирается на предыдущую и считает её завершённой.

### Задача L1 — Локальный запуск без Docker (Windows-first, затем Linux)
- [x] Добавить единый entrypoint локального запуска для разработчика без Docker:
  - `python -m noty.cli setup` — проверка Python/venv, установка зависимостей, генерация `.env` из шаблона.
  - `python -m noty.cli run` — запуск Noti с читаемыми логами и health-статусом.
- [x] Подготовить кросс-платформенные скрипты:
  - `scripts/setup.ps1` (Windows приоритет),
  - `scripts/setup.sh` (Linux).
- [x] Убрать обязательность Telegram из first-run профиля (VK + LLM + SQLite + Mem0/Qdrant как обязательные/условно-обязательные по флагам).
- [x] Добавить минимальный Quick Start в README (без Docker).

**Критерий приёмки:** чистая машина разработчика -> `setup` -> `run` без ручной правки кода и без Docker.

### Задача L2 — Веб-панель конфигурации и запуска (localhost)
- [x] Добавить web-панель (например FastAPI + минимальный UI) в модуле `noty/config/`:
  - форма для ключей/параметров (VK, LLM, Mem0/Qdrant, SQLite),
  - редактор prompt-конфигов,
  - экран текущей personality-версии и причины изменений.
- [x] Реализовать безопасное сохранение в `.env`/конфиги и reload runtime-настроек.
- [x] Добавить кнопки: «Сохранить», «Запустить Noti», «Остановить Noti», «Статус сервиса».
- [x] Добавить базовую авторизацию для локальной панели (пароль из `.env`).
- [x] Расширить web-панель полным просмотром runtime/interactions/thoughts/actions логов и обновлением в UI.
- [x] Добавить в web-панель локальный чат-симулятор для прямых запросов к Ноти (изолированный scope `web_panel`).
- [x] Добавить диагностику чат-симулятора в web-панели: фоновые задачи, request_id статусы, health endpoint и трассировку этапов обработки.

**Критерий приёмки:** после `run` пользователь открывает localhost-панель, настраивает параметры и запускает Noti без ручного редактирования файлов.

### Задача L3 — «Блокнотик Ноти» (малый, управляемый самой Ноти)
- [x] Добавить отдельный модуль заметок: `noty/memory/notebook.py` + таблицу SQLite `noti_notebook`.
- [x] Реализовать tool-call интерфейс для Ноти:
  - `notebook_add`, `notebook_update`, `notebook_delete`, `notebook_list`.
- [x] Ограничить размер блокнота (жёсткий лимит записей/символов) и явно сообщать лимит в prompt слое.
- [x] Встроить notebook в Dynamic Context Builder как приоритетный «не забыть» слой.
- [x] Логировать изменения блокнота в `.jsonl` архив.

**Критерий приёмки:** Ноти умеет сама сохранять/править короткие важные заметки, знает что блокнот ограничен, и использует их в ответах.

### Задача L4 — «Память последних дней» (rolling memory поверх текущих слоёв)
- [x] Добавить слой скользящей памяти последних N дней: `noty/memory/recent_days_memory.py`.
- [x] Механика затухания важности: свежие события влияют сильнее, старые медленно ослабевают.
- [x] Интегрировать слой в Dynamic Context Builder отдельно от semantic/recent/important, чтобы формировать устойчивую «личность во времени».
- [x] Добавить периодический maintenance-job (сжатие/очистка/пересчёт весов).
- [x] Обновить метрики и логи: доля фактов из rolling memory в финальном контексте.

**Критерий приёмки:** Ноти стабильно помнит «фон последних дней» между сессиями и чатами (с учётом chat-scope), без резких провалов контекста.

## M. Bugfix-итерация (диагностика first-run и логирование)
- [x] Расширить параметры запуска `main.py` и `noty.cli run` для управления логированием (`--log-level`, `--log-file`).
- [x] Добавить fallback лог-уровня через `NOTY_LOG_LEVEL` и запись в файл логов с автосозданием директории.
- [x] Добавить smoke-тесты для конфигурации логгера и прокидывания лог-параметров из CLI.
