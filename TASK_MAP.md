
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
- [ ] Добавить в `noty/core/response_processor.py` обязательную проверку ролей перед каждым `tool_call` с блокировкой выполнения при недостаточных правах.  
  **Критерий приемки:** `ResponseProcessor` возвращает статус `denied` и не вызывает executor для пользователя без роли модератора/админа.  
  **Тестовый артефакт:** новый `tests/core/test_response_processor_tool_roles.py`.
- [ ] Реализовать в `noty/tools/safe_tool_executor.py` двухшаговое подтверждение для опасных действий (`ban/mute/delete`) с idempotency-ключом.  
  **Критерий приемки:** первый вызов опасного действия возвращает `confirmation_required`, повтор с тем же ключом исполняет действие ровно один раз.  
  **Тестовый артефакт:** новый `tests/tools/test_safe_tool_executor_confirmations.py`.
- [ ] Привязать модерационные `tool_call` к платформенным адаптерам в `noty/transport/*` (VK/TG) с унифицированным форматом результата.  
  **Критерий приемки:** для `ban_user` и `delete_message` transport-слой возвращает нормализованный payload (`status`, `platform_action_id`, `chat_id`).  
  **Тестовый артефакт:** новый `tests/transport/test_moderation_actions.py`.
- [ ] Добавить в `noty/core/response_processor.py` пост-обработку результата tools (обновление mood/relationship только при `success`).  
  **Критерий приемки:** при `success` обновления выполняются, при `denied/failed` изменения отношения и настроения не применяются.  
  **Тестовый артефакт:** существующий `tests/core/test_response_processor.py` (расширить кейсами).

### Фаза 6: Монолог
- [x] Учет мыслей в выборе стратегий и тональности.

### Фаза 7: Самомодификация
- [x] Approve/reject workflow и rollback personality.

### Фаза 8: Мультичатность
- [ ] В `noty/memory/session_state.py` ввести namespace-ключи состояния вида `{platform}:{chat_id}:{user_id}` для полной изоляции сессий.  
  **Критерий приемки:** записи/чтение состояния для одного чата не влияют на другой чат того же пользователя.  
  **Тестовый артефакт:** новый `tests/memory/test_session_state_namespaces.py`.
- [ ] В `noty/core/context_manager.py` разделить сбор recent/semantic/important контекста по `chat_id` и `thread_id`.  
  **Критерий приемки:** контекст, собранный для одного чата, не содержит сообщений и памяти из другого чата.  
  **Тестовый артефакт:** новый `tests/core/test_context_manager_multichat.py`.
- [ ] Тест-долг: добавить `tests/test_context_manager_multichat.py` для изоляции recent/semantic/important контекста по `chat_id` и `thread_id`.
- [ ] В `noty/transport/router.py` добавить маршрутизацию событий с обязательной передачей `platform`, `chat_id`, `user_id` в pipeline.  
  **Критерий приемки:** каждое входящее событие получает стабильный routing-key, который используется всеми downstream-модулями.  
  **Тестовый артефакт:** новый `tests/transport/test_router_multichat_routing.py`.
- [ ] Добавить очистку и TTL в `noty/memory/session_state.py` на уровне namespace, чтобы истечение одной сессии не затрагивало соседние.  
  **Критерий приемки:** истекший namespace удаляется выборочно, активные namespace остаются доступными.  
  **Тестовый артефакт:** существующий `tests/memory/test_session_state.py` (добавить сценарии TTL-изоляции).
- [ ] Тест-долг: добавить `tests/test_session_state_ttl_namespaces.py` для выборочного TTL-expire по namespace.

### Фаза 9: Полировка
- [ ] Реализовать в `noty/utils/metrics.py` отдельные метрики p50/p95 latency и token-cost по этапам pipeline (filter/context/prompt/llm/tools).  
  **Критерий приемки:** метрики экспортируются с тегами этапа и платформы, доступны для сравнения до/после оптимизаций.  
  **Тестовый артефакт:** новый `tests/utils/test_metrics_pipeline_stages.py`.
- [ ] Тест-долг: добавить `tests/test_metrics_pipeline_stages.py` для проверки p50/p95 и token-cost по stage/platform тегам.
- [ ] В `noty/filters/*` добавить кэширование embedding-результатов и батчирование запросов для однотипных сообщений.  
  **Критерий приемки:** повторная фильтрация идентичного текста использует кэш и снижает количество внешних вызовов.  
  **Тестовый артефакт:** новый `tests/filters/test_embedding_cache.py`.
- [ ] Тест-долг: добавить `tests/test_embedding_cache_batching.py` для cache-hit и batching-сценариев.
- [ ] В `noty/core/api_rotator.py` внедрить адаптивный выбор провайдера по стоимости/задержке с fallback при деградации.  
  **Критерий приемки:** при превышении latency/error-threshold текущий провайдер автоматически заменяется на следующий доступный.  
  **Тестовый артефакт:** существующий `tests/core/test_api_rotator.py` (расширить сценариями деградации).
- [ ] Тест-долг: добавить `tests/test_api_rotator_adaptive_fallback.py` для переключения провайдера при деградации latency/error.
- [ ] Добавить в `noty/utils/metrics.py` и `noty/filters/*` алерт на отклонение respond-rate от целевого коридора (20% ± допуск).  
  **Критерий приемки:** при выходе за порог формируется событие алерта с причиной (перефильтрация/недофильтрация).  
  **Тестовый артефакт:** новый `tests/filters/test_respond_rate_alerts.py`.
- [ ] Тест-долг: добавить `tests/test_respond_rate_alerts.py` для причинных алертов per-filter-state.

### Фаза 10: Telegram
- [x] Завершить адаптер и общий routing слой.


## Матрица: задача -> тест

| Фаза / подзадача | Целевой тестовый файл (`tests/`) | Сценарий проверки | Статус |
|---|---|---|---|
| 5. Проверка ролей перед `tool_call` | `tests/test_tool_execution_pipeline.py` | Немодератор инициирует `tool_call`: `ResponseProcessor` должен вернуть `denied` и не вызвать executor. | нужно обновить |
| 5. Двухшаговое подтверждение + idempotency | `tests/test_tool_confirmation_idempotency.py` | 1-й вызов опасного tool -> `confirmation_required`; 2-й с тем же ключом -> ровно одно исполнение. | нужно обновить |
| 5. Привязка moderation tool calls к VK/TG адаптерам | `tests/test_chat_control_gateways.py` | `ban_user` / `delete_message` возвращают нормализованный payload: `status`, `platform_action_id`, `chat_id`. | нужно обновить |
| 5. Пост-обработка tools только при `success` | `tests/test_tool_execution_pipeline.py` | `mood`/`relationship` меняются только при `success`, при `denied/failed` — без изменений. | нужно обновить |
| 8. Namespace-изоляция session state | `tests/test_multichat_isolation.py` | Ключи `{platform}:{chat_id}:{user_id}` не допускают утечек состояния между чатами одного пользователя. | нужно обновить |
| 8. Context Builder по `chat_id`/`thread_id` | `tests/test_multichat_isolation.py` | `recent/semantic/important` контекст одного чата/треда не содержит данные другого. | нужно обновить |
| 8. Router routing-key и обязательные поля | `tests/test_transport_event_contract.py` | Каждое событие несет `platform`, `chat_id`, `user_id`; routing-key стабилен и пробрасывается вниз по pipeline. | нужно обновить |
| 8. TTL очистка по namespace | `tests/test_multichat_isolation.py` | Истечение TTL удаляет только целевой namespace, соседние активные сессии сохраняются. | нужно обновить |
| 9. Метрики p50/p95 и token-cost по stage/platform | `tests/test_metrics_pipeline_stages.py` | Экспортируются latency/token-cost метрики по этапам `filter/context/prompt/llm/tools` с тегом платформы. | нужно добавить |
| 9. Embedding cache + batching | `tests/test_embedding_cache_batching.py` | Повторный одинаковый текст даёт cache-hit; однотипные сообщения обрабатываются батчем с меньшим числом внешних вызовов. | нужно добавить |
| 9. Adaptive provider fallback | `tests/test_api_rotator_adaptive_fallback.py` | При деградации latency/error выполняется автоматическое переключение на следующий доступный провайдер. | нужно добавить |
| 9. Respond-rate alerts | `tests/test_respond_rate_alerts.py` | При выходе за коридор 20% ± допуск создаётся алерт с причиной `перефильтрация/недофильтрация`. | нужно добавить |

---

## Приоритет следующего итерационного цикла
1. Реальный VK ingestion + сквозной MVP.
2. Метрики фильтрации и стоимости.
3. Автообновление памяти/отношений после ответа.
4. Тестовый контур.
