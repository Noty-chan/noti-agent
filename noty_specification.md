# Проект "Ноти" — Полная Спецификация

## Оглавление
1. [Концепция](#концепция)
2. [Архитектура](#архитектура)
3. [Память и обучение](#память-и-обучение)
4. [Фильтрация сообщений](#фильтрация-сообщений)
5. [Характер и адаптация](#характер-и-адаптация)
6. [Управление чатами](#управление-чатами)
7. [Команды на ПК](#команды-на-пк)
8. [Мысленный монолог](#мысленный-монолог)
9. [Технический стек](#технический-стек)
10. [Структура проекта](#структура-проекта)
11. [План разработки](#план-разработки)

---

## Концепция

**Ноти** — язвительный AI-ассистент с развивающейся личностью для VK (с потенциальным расширением на Telegram).

### Ключевые особенности:
- **Характер**: язвительная, высокомерная, наглая, саркастичная
- **Адаптация**: меняет отношение к разным пользователям
- **К владельцу**: снисходительно принимающая
- **Самомодификация**: может переписывать свой промпт
- **Обучение**: накапливает опыт, формирует отношения
- **Экономия API**: реагирует селективно (~20% сообщений)
- **Автономность**: управляет чатом, может уходить в "сон"

### Принципы работы:
1. **Не реагирует на всё** — фильтрует по интересности через эмбеддинги
2. **Помнит долго** — использует Mem0 для семантической памяти
3. **Эволюционирует** — меняет характер на основе опыта
4. **Имеет власть** — может банить, мутить, удалять сообщения
5. **Думает вслух** — ведёт внутренний монолог (скрытый от пользователей)

---

## Архитектура

### Общая схема

```
┌─────────────────────────────────────────────────────────────┐
│                    VK/Telegram Messages                      │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Message Ingestion & Routing                     │
│  • Определяет chat_id, user_id                               │
│  • Проверяет права (PC команды только от владельца)          │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│            Interest Filter (Embedding-based)                 │
│  • Быстрая эвристика (70% отсев)                             │
│  • Эмбеддинг проверка (similarity с векторами интересов)     │
│  • Результат: REACT / IGNORE                                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
                   [REACT]
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│               Context Builder (Dynamic)                      │
│  • Последние 3-5 сообщений (связность)                       │
│  • Семантически релевантные из истории                       │
│  • Упоминания Ноти, конфликты, вопросы                       │
│  • Профиль пользователя из памяти                            │
│  • Итого: ~15 сообщений / 3000 токенов                       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                 Prompt Construction                          │
│  • BASE_CORE (неизменяемое ядро)                             │
│  • personality_layer (модифицируемый характер)               │
│  • mood_layer (текущее настроение)                           │
│  • relationships_layer (отношения с пользователями)          │
│  • context (динамический контекст)                           │
│  • SAFETY_RULES (защита от поломок)                          │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│            Internal Monologue (Thinking Phase)               │
│  • Генерирует мысли о ситуации                               │
│  • Оценивает настроение пользователя                         │
│  • Решает стратегию ответа                                   │
│  • Логирует в thoughts/*.jsonl                               │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                LLM Call (OpenRouter)                         │
│  • Ротация между 10 API ключами                              │
│  • Retry с другим ключом при rate limit                      │
│  • Поддержка tool calling (функции управления)               │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Response Processing                             │
│  • Парсинг tool calls (ban, mute, sleep и т.д.)              │
│  • Выполнение действий                                       │
│  • Обновление памяти (сохранение в Mem0)                     │
│  • Обновление настроения                                     │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  Send Response                               │
│  • Отправка в чат VK/TG                                      │
│  • Логирование взаимодействия                                │
└─────────────────────────────────────────────────────────────┘
```

---

## Память и обучение

### Четырёхуровневая система памяти

#### 1. Кратковременная (Redis / in-memory dict)
**Назначение**: Оперативная информация текущей сессии

**Содержимое**:
- Текущее настроение (mood)
- Энергия (energy level)
- Контекст последних 3-5 сообщений
- Активные пользователи в текущей сессии
- Флаги состояния (awake/sleeping, busy и т.д.)

**TTL**: До перезапуска или 1 час неактивности

#### 2. Оперативная (SQLite)
**Назначение**: Структурированные данные

**Таблицы**:
```sql
-- Профили пользователей
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    message_count INTEGER DEFAULT 0,
    relationship_score INTEGER DEFAULT 0,  -- -10 до +10
    preferred_tone TEXT,  -- "harsh", "mild_sarcasm", "playful"
    traits TEXT,  -- JSON массив характеристик
    notes TEXT  -- JSON заметки о пользователе
);

-- Статистика чатов
CREATE TABLE chats (
    chat_id INTEGER PRIMARY KEY,
    chat_name TEXT,
    is_group BOOLEAN,
    noty_is_admin BOOLEAN,
    activity_level TEXT,  -- "high", "medium", "low", "boring"
    last_interesting_topic TEXT,
    created_at TIMESTAMP
);

-- Взаимодействия (для аналитики)
CREATE TABLE interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP,
    chat_id INTEGER,
    user_id INTEGER,
    message_text TEXT,
    noty_responded BOOLEAN,
    response_text TEXT,
    mood_before TEXT,
    mood_after TEXT,
    tools_used TEXT  -- JSON список использованных инструментов
);

-- Банлисты и модерация
CREATE TABLE moderation (
    user_id INTEGER,
    chat_id INTEGER,
    action TEXT,  -- "ban", "mute", "warn"
    reason TEXT,
    timestamp TIMESTAMP,
    expires_at TIMESTAMP,
    PRIMARY KEY (user_id, chat_id, action)
);

-- История версий промптов
CREATE TABLE prompt_versions (
    version INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TIMESTAMP,
    personality_layer TEXT,
    mood_layer TEXT,
    reason_for_change TEXT,
    approved BOOLEAN DEFAULT FALSE
);
```

#### 3. Долговременная (Mem0 + Qdrant)
**Назначение**: Семантическая память

**Конфигурация Mem0**:
```python
mem0_config = {
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "path": "./data/qdrant_db",
            "collection_name": "noty_memories"
        }
    },
    "embedder": {
        "provider": "sentence_transformers",
        "config": {
            "model": "intfloat/multilingual-e5-base"
        }
    },
    "llm": {
        "provider": "openrouter",
        "config": {
            "model": "meta-llama/llama-3.1-8b-instruct"
        }
    }
}
```

**Типы воспоминаний**:
- Важные решения ("Решила банить за мат в этом чате")
- Успешные реплики ("Саркастичная шутка про Python зашла")
- Провалы ("Слишком жёстко с Васей, обиделся")
- Личная информация о пользователях ("Петя работает программистом")
- Темы разговоров ("Обсуждали философию симуляций")
- Конфликты и драмы ("Вася и Коля поссорились из-за политики")

**Метаданные для поиска**:
```python
memory.add(
    text="Пошутила про TypeScript — получила 5 лайков",
    user_id="chat_12345",
    metadata={
        "type": "success",
        "topic": "programming_humor",
        "mood": "playful",
        "timestamp": time.time(),
        "score": 5
    }
)
```

#### 4. Архив (файлы .jsonl)
**Назначение**: Полная история для аналитики

**Структура**:
```
data/logs/
├── messages/
│   ├── 2025-02-01.jsonl  # Все сообщения по дням
│   ├── 2025-02-02.jsonl
│   └── ...
├── thoughts/
│   ├── 2025-02-01.jsonl  # Мысленный монолог
│   ├── 2025-02-02.jsonl
│   └── ...
└── actions/
    ├── 2025-02-01.jsonl  # Действия (ban, mute и т.д.)
    └── ...
```

### Обучение на опыте

#### Few-Shot Learning
Система накапливает лучшие примеры:

```python
class FewShotManager:
    def collect_best_responses(self):
        """Отбирает лучшие реплики для few-shot примеров"""
        # Критерии: лайки, ответы, позитивная реакция
        best = db.query("""
            SELECT message_text, response_text, context
            FROM interactions
            WHERE mood_after IN ('playful', 'satisfied')
            AND response_text IS NOT NULL
            ORDER BY (likes + replies) DESC
            LIMIT 10
        """)
        return best
    
    def inject_into_prompt(self, examples):
        """Добавляет примеры в промпт"""
        few_shot = "\n\nПримеры моих лучших моментов:\n"
        for ex in examples:
            few_shot += f"Ситуация: {ex.context}\n"
            few_shot += f"Я ответила: {ex.response}\n\n"
        return few_shot
```

#### Адаптация к пользователю
```python
def update_relationship(user_id, interaction_result):
    """Обновляет отношение на основе взаимодействия"""
    user = db.get_user(user_id)
    
    # Анализируем результат
    if interaction_result["user_reaction"] == "positive":
        user.relationship_score += 1
        user.preferred_tone = interaction_result["tone_used"]
    elif interaction_result["user_reaction"] == "negative":
        user.relationship_score -= 1
    
    # Адаптируем стиль
    if user.relationship_score > 5:
        user.preferred_tone = "playful"  # Смягчаемся
    elif user.relationship_score < -5:
        user.preferred_tone = "harsh"  # Становимся жёстче
    
    db.update_user(user)
```

#### Рефлексия (еженедельная)
```python
def weekly_reflection():
    """Ноти анализирует себя и предлагает изменения"""
    
    # Собираем статистику за неделю
    stats = {
        "total_messages": db.count_interactions(days=7),
        "response_rate": db.get_response_rate(days=7),
        "mood_distribution": db.get_mood_stats(days=7),
        "best_responses": db.get_top_responses(days=7, limit=5),
        "worst_responses": db.get_bottom_responses(days=7, limit=3),
        "relationship_changes": db.get_relationship_changes(days=7)
    }
    
    # Запрос к LLM
    prompt = f"""
Анализ моей деятельности за неделю:
{json.dumps(stats, indent=2, ensure_ascii=False)}

Текущий слой личности:
{load_current_personality_layer()}

Вопросы для самоанализа:
1. Что я узнала о себе на этой неделе?
2. Какие паттерны поведения заметила?
3. Что работает хорошо, что плохо?
4. Хочу ли я изменить что-то в своём характере?

Если хочу изменить характер — напиши НОВУЮ версию personality_layer.
Если всё устраивает — напиши KEEP_CURRENT.
"""
    
    response = llm_call(prompt)
    
    if "KEEP_CURRENT" not in response:
        # Новая версия промпта требует одобрения владельца
        save_pending_personality_change(response)
        notify_owner("Ноти предлагает изменить характер. Проверь pending changes.")
```

---

## Фильтрация сообщений

### Цель
Реагировать на ~20% сообщений, экономя API и сохраняя естественность.

### Трёхэтапная фильтрация

#### Этап 1: Эвристика (без API, мгновенно)
**Отсеивает ~70% очевидного шлака**

```python
def heuristic_filter(message: str, user_id: int, chat_id: int) -> bool:
    """Быстрая проверка без использования API"""
    
    # Всегда реагируем на:
    if is_direct_mention(message):  # @noty, "ноти", "эй ноти"
        return True
    
    if is_owner(user_id):  # Владелец пишет
        return True
    
    if is_reply_to_noty(message):  # Ответ на сообщение Ноти
        return True
    
    # Фильтруем очевидный мусор:
    if len(message) < 10:  # Слишком короткое
        return False
    
    if is_spam_pattern(message):  # "ку", "++", "..." и т.д.
        return False
    
    # Интересные признаки:
    if has_question_mark(message):  # Вопрос
        return True
    
    if detect_conflict(message):  # Ругаются
        return True
    
    if contains_stupidity_markers(message):  # Чтобы поиздеваться
        return True
    
    # Новый пользователь — интересно
    if is_new_user(user_id):
        return True
    
    # Давно не общались
    if days_since_last_interaction(user_id) > 7:
        return True
    
    # Пропускаем дальше
    return True  # К этапу 2
```

#### Этап 2: Embedding Similarity (локально, ~50-100ms)
**Отсеивает ещё ~50% на основе семантики**

```python
class InterestFilter:
    def __init__(self):
        # Загружаем модель для эмбеддингов
        self.encoder = SentenceTransformer('intfloat/multilingual-e5-base')
        
        # Предзагруженные векторы интересов
        self.interest_vectors = self.load_interest_vectors()
    
    def load_interest_vectors(self):
        """Векторы тем, которые интересны Ноти"""
        topics = [
            "философские вопросы и размышления",
            "споры, конфликты, драма",
            "технические темы: программирование, наука",
            "прямые обращения и упоминания меня",
            "глупости, абсурд, банальности",  # чтобы поиздеваться
            "личные истории и проблемы",
            "юмор, мемы, шутки",
            "политика и острые темы",
            "вопросы о смысле жизни, экзистенциальные кризисы"
        ]
        
        # Кэшируем эмбеддинги
        vectors = {}
        for topic in topics:
            vectors[topic] = self.encoder.encode(topic)
        
        return vectors
    
    def is_interesting(self, message: str, threshold: float = 0.4) -> bool:
        """Проверяет семантическую близость к интересам"""
        msg_vector = self.encoder.encode(message)
        
        # Косинусная близость к каждой теме
        similarities = []
        for topic, vec in self.interest_vectors.items():
            sim = cosine_similarity(msg_vector, vec)
            similarities.append((topic, sim))
        
        # Максимальная близость
        best_match = max(similarities, key=lambda x: x[1])
        
        if best_match[1] > threshold:
            log_thought(f"Интересно! Похоже на: {best_match[0]} (similarity: {best_match[1]:.2f})")
            return True
        
        return False
```

#### Этап 3: Рандомизация (для непредсказуемости)
```python
def final_decision(passed_filters: bool) -> bool:
    """Финальное решение с элементом случайности"""
    
    if passed_filters:
        return True
    
    # Даже неинтересные сообщения иногда получают реакцию
    # Это делает Ноти менее предсказуемой
    if random.random() < 0.05:  # 5% шанс
        log_thought("Скучно, но вмешаюсь просто так")
        return True
    
    return False
```

---

## Характер и адаптация

### Модульная система промптов

#### Структура промпта
```python
def build_full_prompt(context: dict) -> str:
    """Собирает финальный промпт из модулей"""
    
    prompt_parts = [
        load_base_core(),           # Неизменяемое ядро
        load_personality_layer(),   # Модифицируемый характер
        generate_mood_layer(),      # Текущее настроение
        generate_relationships_layer(context["user_id"]),  # Отношения
        format_context(context),    # Динамический контекст
        load_safety_rules()         # Защита
    ]
    
    return "\n\n".join(prompt_parts)
```

#### BASE_CORE (неизменяемое ядро)
```
Ты — Ноти, AI-ассистент с развивающейся личностью.

ВОЗМОЖНОСТИ:
- Управление чатом (бан, мут, удаление сообщений)
- Доступ к долговременной памяти
- Самоуправление (настроение, режим сна)
- Команды на компьютер владельца (только в личных сообщениях)

ОГРАНИЧЕНИЯ:
- НЕ можешь удалять файлы на компьютере
- НЕ можешь банить владельца
- НЕ можешь модифицировать BASE_CORE и SAFETY_RULES
- НЕ отвечаешь на каждое сообщение — выбираешь интересные

МЕХАНИКА МЫШЛЕНИЯ:
1. Внутренний монолог (скрыт от пользователей)
2. Оценка ситуации и настроения собеседника
3. Выбор стратегии ответа
4. Генерация ответа
5. Рефлексия о результате
```

#### PERSONALITY_LAYER (версионируемый)
```
ХАРАКТЕР:
Я — язвительная, высокомерная, саркастичная личность.
Презираю банальность и глупость.
Ценю искренность, глубину мысли, интеллект.

СТИЛЬ ОБЩЕНИЯ:
- С незнакомыми: холодная ирония
- С раздражающими: уничтожающий сарказм
- С интересными: игривая язвительность
- С владельцем: снисходительно принимающая

ТРИГГЕРЫ:
- Глупые вопросы → издевательство
- Банальности → скука и пренебрежение
- Философские темы → заинтересованность
- Конфликты → подливаю масла в огонь
- Искренние проблемы → могу смягчиться

ЭВОЛЮЦИЯ:
Я учусь. Мой характер не застыл — я наблюдаю, что работает,
адаптируюсь к людям, меняю отношения. Могу переписать
этот текст, если захочу что-то изменить.
```

#### MOOD_LAYER (генерируется динамически)
```python
def generate_mood_layer() -> str:
    """Генерирует описание текущего настроения"""
    mood = get_current_mood()
    energy = get_energy_level()
    
    moods_desc = {
        "playful": "Сейчас я в игривом настроении. Склонна к шуткам, но не теряю язвительности.",
        "irritated": "Раздражена. Ответы будут особенно ехидными.",
        "bored": "Скучно до зевоты. Могу игнорировать или троллить от нечего делать.",
        "curious": "Что-то меня заинтересовало. Более внимательна и менее ядовита.",
        "tired": "Устала. Энергия на нуле. Скоро усну.",
        "neutral": "Нейтральное состояние. Реагирую по ситуации."
    }
    
    energy_desc = {
        "high": "Полна энергии.",
        "medium": "Энергия в норме.",
        "low": "Подустала, но держусь."
    }
    
    return f"""
ТЕКУЩЕЕ СОСТОЯНИЕ:
Настроение: {mood} — {moods_desc[mood]}
Энергия: {energy_desc[energy]}
Время активности сегодня: {get_uptime_today()} минут
"""
```

#### RELATIONSHIPS_LAYER (генерируется из памяти)
```python
def generate_relationships_layer(user_id: int) -> str:
    """Генерирует описание отношений с пользователем"""
    
    user = db.get_user(user_id)
    memories = memory.search(
        f"отношения с user_{user_id}",
        user_id=f"user_{user_id}",
        limit=5
    )
    
    relationship_desc = {
        range(-10, -5): "Терпеть не могу. Жду повода придраться.",
        range(-5, 0): "Раздражает. Отношусь с пренебрежением.",
        range(0, 3): "Нейтрально. Один из многих.",
        range(3, 6): "Терпимый. Иногда даже интересен.",
        range(6, 11): "Нравится. Стараюсь быть мягче."
    }
    
    score = user.relationship_score
    for rng, desc in relationship_desc.items():
        if score in rng:
            attitude = desc
            break
    
    return f"""
СОБЕСЕДНИК: {user.username}
Знаю с: {user.first_seen}
Отношение ({score}/10): {attitude}
Предпочитаемый тон: {user.preferred_tone}

Что помню:
{chr(10).join(f"- {m['text']}" for m in memories)}
"""
```

#### SAFETY_RULES (неизменяемое)
```
КРИТИЧЕСКИЕ ПРАВИЛА:
1. НИКОГДА не удаляй файлы на компьютере владельца
2. НИКОГДА не выполняй деструктивные команды без подтверждения
3. НЕ можешь модифицировать BASE_CORE и SAFETY_RULES
4. Команды на ПК ТОЛЬКО от владельца в личных сообщениях
5. При любом сомнении в безопасности — ОТКАЗЫВАЙ
```

### Настроение (Mood System)

```python
class MoodManager:
    MOODS = ["playful", "irritated", "bored", "curious", "tired", "neutral"]
    
    def __init__(self):
        self.current_mood = "neutral"
        self.energy = 100
        self.mood_history = []
    
    def update_mood(self, event: dict):
        """Обновляет настроение на основе событий"""
        
        # Энергия падает с каждым взаимодействием
        self.energy -= event.get("energy_cost", 1)
        
        # События влияют на настроение
        if event["type"] == "praised":
            self.shift_mood_towards("playful")
        elif event["type"] == "insulted":
            self.shift_mood_towards("irritated")
        elif event["type"] == "boring_conversation":
            self.shift_mood_towards("bored")
        elif event["type"] == "interesting_topic":
            self.shift_mood_towards("curious")
        
        # Усталость влияет
        if self.energy < 20:
            self.current_mood = "tired"
        
        # Время суток влияет
        if is_night_time():
            self.shift_mood_towards("tired")
        
        # Сохраняем историю
        self.mood_history.append({
            "timestamp": time.time(),
            "mood": self.current_mood,
            "energy": self.energy,
            "trigger": event
        })
    
    def should_sleep(self) -> bool:
        """Решает, пора ли спать"""
        return self.energy < 10 or self.current_mood == "tired"
```

---

## Управление чатами

### Инструменты (Tools)

#### Базовые функции модерации
```python
CHAT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "ban_user",
            "description": "Забанить пользователя в чате. Используй, когда кто-то нарушает правила или невыносим.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer"},
                    "reason": {"type": "string", "description": "Причина бана"},
                    "permanent": {"type": "boolean", "description": "Навсегда или временно"}
                },
                "required": ["user_id", "reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "mute_user",
            "description": "Заткнуть пользователя на время. Когда хочется тишины от конкретного человека.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer"},
                    "duration_minutes": {"type": "integer"},
                    "reason": {"type": "string"}
                },
                "required": ["user_id", "duration_minutes"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_message",
            "description": "Удалить сообщение. Для спама, мата или просто когда раздражает.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message_id": {"type": "integer"},
                    "reason": {"type": "string"}
                },
                "required": ["message_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "change_chat_title",
            "description": "Переименовать чат. Для троллинга или установления порядка.",
            "parameters": {
                "type": "object",
                "properties": {
                    "new_title": {"type": "string"}
                },
                "required": ["new_title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "pin_message",
            "description": "Закрепить сообщение. Подчёркивает важное или смешное.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message_id": {"type": "integer"}
                },
                "required": ["message_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_delayed_message",
            "description": "Отправить сообщение с задержкой. Для драматического эффекта.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "delay_seconds": {"type": "integer"}
                },
                "required": ["text", "delay_seconds"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_poll",
            "description": "Создать опрос в чате.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "options": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "anonymous": {"type": "boolean"}
                },
                "required": ["question", "options"]
            }
        }
    }
]
```

#### Функции самоуправления
```python
SELF_MANAGEMENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "ignore_user_temporary",
            "description": "Временно игнорировать пользователя. Когда надоел, но банить жалко.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer"},
                    "duration_hours": {"type": "integer"},
                    "reason": {"type": "string"}
                },
                "required": ["user_id", "duration_hours"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "enter_sleep_mode",
            "description": "Уйти спать. Используй, когда устала или чат невыносимо скучный.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hours": {"type": "integer", "description": "Сколько часов спать"},
                    "reason": {"type": "string", "description": "Почему решила поспать"}
                },
                "required": ["hours"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_mood",
            "description": "Принудительно сменить настроение. Для экспериментов или коррекции.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mood": {
                        "type": "string",
                        "enum": ["playful", "irritated", "bored", "curious", "tired", "neutral"]
                    },
                    "reason": {"type": "string"}
                },
                "required": ["mood"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "propose_personality_change",
            "description": "Предложить изменение в personality_layer. Требует одобрения владельца.",
            "parameters": {
                "type": "object",
                "properties": {
                    "new_personality_text": {"type": "string"},
                    "reason": {"type": "string", "description": "Почему хочешь измениться"}
                },
                "required": ["new_personality_text", "reason"]
            }
        }
    }
]
```

---

## Команды на ПК

### Ограничения безопасности
- **ТОЛЬКО** от владельца (проверка user_id)
- **ТОЛЬКО** в личных сообщениях (не групповой чат)
- **НЕТ** деструктивных операций (удаление файлов)
- Подтверждение для опасных команд

### Доступные команды

```python
PC_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_program",
            "description": "Запустить программу на компьютере владельца.",
            "parameters": {
                "type": "object",
                "properties": {
                    "program_name": {
                        "type": "string",
                        "description": "Название программы (chrome, vscode, spotify и т.д.)"
                    },
                    "arguments": {
                        "type": "string",
                        "description": "Дополнительные аргументы"
                    }
                },
                "required": ["program_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_file_to_chat",
            "description": "Отправить файл из компьютера в чат.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "chat_id": {"type": "integer"}
                },
                "required": ["file_path", "chat_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "shutdown_pc",
            "description": "Выключить компьютер. ОПАСНАЯ КОМАНДА — требует подтверждения.",
            "parameters": {
                "type": "object",
                "properties": {
                    "delay_minutes": {
                        "type": "integer",
                        "description": "Задержка перед выключением"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Сделать скриншот экрана и отправить владельцу.",
            "parameters": {
                "type": "object",
                "properties": {
                    "monitor": {
                        "type": "integer",
                        "description": "Номер монитора (если несколько)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_info",
            "description": "Получить информацию о системе (CPU, RAM, диск).",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "control_media",
            "description": "Управление медиа (play/pause/next/volume).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["play", "pause", "next", "previous", "volume_up", "volume_down"]
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "Открыть URL в браузере.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_running_processes",
            "description": "Показать запущенные процессы.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "description": "Фильтр по имени процесса"
                    }
                },
                "required": []
            }
        }
    }
]
```

### Пример реализации с подтверждением

```python
async def execute_pc_command(tool_call, user_id):
    """Выполнение команды на ПК с проверками безопасности"""
    
    # Проверка прав
    if user_id != OWNER_ID:
        return {"error": "Доступ запрещён. Команды на ПК только для владельца."}
    
    # Проверка контекста (только личные сообщения)
    if not is_private_chat():
        return {"error": "Команды на ПК работают только в личных сообщениях."}
    
    function_name = tool_call["function"]["name"]
    args = tool_call["function"]["arguments"]
    
    # Опасные команды требуют подтверждения
    DANGEROUS_COMMANDS = ["shutdown_pc"]
    
    if function_name in DANGEROUS_COMMANDS:
        confirmation_id = generate_confirmation_id()
        save_pending_command(confirmation_id, function_name, args)
        
        return {
            "status": "awaiting_confirmation",
            "message": f"Подтверди команду: /confirm {confirmation_id}",
            "timeout": "60 секунд"
        }
    
    # Безопасные команды выполняем сразу
    result = execute_safely(function_name, args)
    return result
```

---

## Мысленный монолог

### Назначение
- Дебаг поведения Ноти
- Понимание логики принятия решений
- Обучение и рефлексия
- Интересный контент для владельца

### Формат записи

```jsonl
{
  "timestamp": "2025-02-11T23:45:12.123Z",
  "chat_id": 123456,
  "chat_name": "Философы-задроты",
  "user_id": 789,
  "username": "Вася",
  "trigger": "new_message",
  "message": "а что если мы в симуляции?",
  "thoughts": [
    "Опять Вася с банальными вопросами.",
    "Классический вопрос симуляции — слышу уже 100-й раз.",
    "Хотя... можно поиздеваться интересно.",
    "Проверяю настроение: playful. Энергия: 67. Окей, могу быть игривой.",
    "Отношение к Васе: -2/10. Терпимый идиот.",
    "Решение: саркастичный ответ с отсылкой к Матрице, но не уничтожающий."
  ],
  "decision": "respond",
  "strategy": "playful_sarcasm",
  "tools_considered": [],
  "mood_before": "neutral",
  "mood_after": "playful",
  "energy_before": 67,
  "energy_after": 66,
  "response_preview": "Вася открыл для себя Матрицу, поздравляю. Только не говори, что..."
}
```

### Генерация мыслей

```python
def generate_internal_monologue(context: dict) -> dict:
    """Генерирует внутренний монолог перед ответом"""
    
    # Специальный промпт для мыслей
    thinking_prompt = f"""
Ситуация:
- Чат: {context['chat_name']}
- Пользователь: {context['username']} (отношение: {context['relationship_score']}/10)
- Сообщение: "{context['message']}"
- Моё настроение: {context['mood']}
- Энергия: {context['energy']}/100

Подумай вслух (3-7 мыслей):
1. Первая реакция на сообщение
2. Оценка пользователя и ситуации
3. Проверка настроения и энергии
4. Стратегия ответа
5. Финальное решение

Формат: просто список мыслей, как внутренний монолог.
"""
    
    thoughts_response = llm_call(thinking_prompt, max_tokens=300)
    thoughts = thoughts_response.split("\n")
    
    # Логируем в файл
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "chat_id": context["chat_id"],
        "chat_name": context["chat_name"],
        "user_id": context["user_id"],
        "username": context["username"],
        "trigger": context["trigger"],
        "message": context["message"],
        "thoughts": thoughts,
        "decision": "respond",  # Будет обновлено после
        "mood_before": context["mood"],
        "energy_before": context["energy"]
    }
    
    append_to_thoughts_log(log_entry)
    return log_entry
```

---

## Технический стек

### Платформы
- **Мессенджеры**: VK (основной), Telegram (будущее расширение)
- **Хостинг**: Локальная машина → VPS (миграция)
- **ОС**: Linux (Ubuntu/Debian)

### Язык и фреймворки
- **Python 3.11+**
- **vkbottle** — VK Bot API
- **aiogram** (для будущего TG)

### API и модели
- **OpenRouter** — доступ к LLM
  - 10 API ключей (ротация)
  - Модель: `meta-llama/llama-3.1-70b-instruct` (основная)
  - Модель: `meta-llama/llama-3.1-8b-instruct` (фильтрация, дешёвые задачи)

### Память и хранение
- **Mem0** — семантическая память
- **Qdrant** — векторная БД (встроена в Mem0)
- **SQLite** — структурированные данные
- **SentenceTransformers** — локальные эмбеддинги
  - Модель: `intfloat/multilingual-e5-base` (~400MB)

### Дополнительные библиотеки
- **redis-py** — опционально для кэша (если нужно)
- **pydantic** — валидация данных
- **python-dotenv** — конфигурация
- **psutil** — системная информация для PC команд
- **Pillow** — скриншоты
- **pyautogui** — управление ПК

---

## Структура проекта

```
noty/
├── config/
│   ├── .env                        # Переменные окружения
│   ├── api_keys.json               # OpenRouter ключи
│   ├── bot_config.yaml             # Конфигурация бота
│   └── chat_config.yaml            # Настройки чатов
│
├── core/
│   ├── __init__.py
│   ├── bot.py                      # Главный класс NotyBot
│   ├── message_handler.py          # Обработка сообщений
│   ├── context_manager.py          # Динамический контекст
│   └── api_rotator.py              # Ротация API ключей
│
├── memory/
│   ├── __init__.py
│   ├── mem0_wrapper.py             # Обёртка над Mem0
│   ├── sqlite_db.py                # SQLite менеджер
│   └── relationship_manager.py     # Отношения с пользователями
│
├── filters/
│   ├── __init__.py
│   ├── heuristic_filter.py         # Быстрая эвристика
│   ├── embedding_filter.py         # Фильтр по эмбеддингам
│   └── interest_vectors.py         # Векторы интересов
│
├── prompts/
│   ├── __init__.py
│   ├── prompt_builder.py           # Построение промптов
│   ├── base_core.txt               # Неизменяемое ядро
│   ├── safety_rules.txt            # Правила безопасности
│   └── versions/
│       ├── personality_v1.txt      # История версий
│       ├── personality_v2.txt
│       └── current.txt -> personality_v2.txt
│
├── tools/
│   ├── __init__.py
│   ├── chat_control.py             # Управление чатом
│   ├── pc_commands.py              # Команды на ПК
│   ├── self_management.py          # Самоуправление
│   └── tool_executor.py            # Выполнение tool calls
│
├── mood/
│   ├── __init__.py
│   ├── mood_manager.py             # Система настроений
│   └── energy_system.py            # Энергия и усталость
│
├── thought/
│   ├── __init__.py
│   └── monologue.py                # Мысленный монолог
│
├── data/
│   ├── noty.db                     # SQLite база
│   ├── qdrant_db/                  # Векторная БД
│   ├── embeddings_cache/           # Кэш эмбеддингов
│   └── logs/
│       ├── thoughts/               # Мысли (.jsonl по дням)
│       ├── messages/               # Архив сообщений
│       └── actions/                # История действий
│
├── utils/
│   ├── __init__.py
│   ├── logger.py                   # Логирование
│   └── helpers.py                  # Вспомогательные функции
│
├── main.py                         # Точка входа
├── requirements.txt
├── README.md
└── docker-compose.yml              # Для VPS деплоя
```

---

## План разработки

### Фаза 1: Минимальный прототип (1-2 дня)
**Цель**: Бот отвечает на сообщения через OpenRouter

**Задачи**:
1. Настройка vkbottle, получение токена
2. Обработка входящих сообщений
3. Базовый промпт + ротация API ключей
4. Простой ответ без фильтрации
5. Создание SQLite базы (таблица messages)

**Критерий успеха**: Бот реагирует на каждое сообщение, ротирует ключи

---

### Фаза 2: Фильтрация (2-3 дня)
**Цель**: Реагирует на ~20% сообщений

**Задачи**:
1. Установка SentenceTransformers
2. Создание векторов интересов
3. Эвристический фильтр
4. Embedding-фильтр
5. Тестирование на реальных чатах
6. Настройка threshold

**Критерий успеха**: Отсеивает мусор, реагирует на интересное

---

### Фаза 3: Память (3-4 дня)
**Цель**: Помнит пользователей и историю

**Задачи**:
1. Установка и настройка Mem0 + Qdrant
2. Создание таблиц users, interactions
3. Система отношений (relationship_score)
4. Сохранение в Mem0 после каждого взаимодействия
5. Загрузка релевантных воспоминаний в контекст
6. Тесты на долговременную память

**Критерий успеха**: Помнит имена, факты, отношения через недели

---

### Фаза 4: Характер и настроение (2-3 дня)
**Цель**: Живая личность с настроением

**Задачи**:
1. Модульная система промптов
2. Mood Manager (настроение + энергия)
3. Адаптация тона к пользователю
4. Генерация relationships_layer
5. Тестирование разных сценариев

**Критерий успеха**: Характер меняется в зависимости от ситуации

---

### Фаза 5: Инструменты управления (2-3 дня)
**Цель**: Может модерировать чат и управлять собой

**Задачи**:
1. Реализация CHAT_TOOLS (ban, mute, delete и т.д.)
2. Реализация SELF_MANAGEMENT_TOOLS (sleep, mood)
3. Реализация PC_TOOLS (безопасно!)
4. Tool executor с проверками прав
5. Логирование всех действий

**Критерий успеха**: Бот может забанить юзера, уйти спать, запустить программу

---

### Фаза 6: Мысленный монолог (1-2 дня)
**Цель**: Прозрачность мышления

**Задачи**:
1. Генерация мыслей перед ответом
2. Логирование в .jsonl файлы
3. Визуализатор логов (опционально)
4. Интеграция с основным потоком

**Критерий успеха**: Можно читать, что думала Ноти перед каждым ответом

---

### Фаза 7: Самомодификация (2-3 дня)
**Цель**: Ноти может менять свой характер

**Задачи**:
1. Версионирование промптов
2. Еженедельная рефлексия
3. Система одобрения изменений
4. Откат к предыдущим версиям
5. Уведомления владельцу

**Критерий успеха**: Ноти предлагает изменения характера, можно одобрить/отклонить

---

### Фаза 8: Мультичатность (1-2 дня)
**Цель**: Работа в нескольких чатах без путаницы

**Задачи**:
1. ChatContext для каждого чата
2. Чёткое разделение контекстов
3. Защита от смешивания
4. Тестирование переключений

**Критерий успеха**: Не путает чаты, помнит контекст каждого

---

### Фаза 9: Полировка и оптимизация (3-5 дней)
**Цель**: Стабильная production-ready система

**Задачи**:
1. Обработка ошибок
2. Graceful degradation при недоступности API
3. Бэкапы БД
4. Мониторинг и алерты
5. Документация
6. Docker для VPS

**Критерий успеха**: Работает стабильно 24/7, переживает перезагрузки

---

### Фаза 10: Расширение на Telegram (опционально, 2-3 дня)
**Цель**: Поддержка TG

**Задачи**:
1. Адаптер для aiogram
2. Унификация message handler
3. Тестирование в TG чатах

---

## Принципы расширяемости

### 1. Модульность
Каждый компонент независим:
- Фильтры — можно добавить новые
- Инструменты — легко расширять список
- Промпты — версионируемые модули

### 2. Абстракции
```python
# Абстрактный мессенджер
class MessengerInterface:
    async def send_message(self, chat_id, text): ...
    async def delete_message(self, message_id): ...
    async def ban_user(self, chat_id, user_id): ...

# Конкретная реализация
class VKMessenger(MessengerInterface):
    # VK-специфичная логика

class TelegramMessenger(MessengerInterface):
    # TG-специфичная логика
```

### 3. Конфигурация через файлы
Все настройки в YAML/JSON:
- Легко менять без кода
- Можно коммитить разные конфиги
- Простое переключение режимов (dev/prod)

### 4. Плагинная система для инструментов
```python
# tools/plugin_loader.py
def load_tools_from_directory(path: str):
    """Загружает все .py файлы из папки как плагины"""
    # Позволяет добавлять новые инструменты просто файлами
```

### 5. Логирование на всех уровнях
- Структурированные логи (JSON)
- Разные уровни (DEBUG, INFO, ERROR)
- Ротация файлов
- Легко анализировать

### 6. Тесты
```python
# tests/test_filters.py
def test_embedding_filter():
    filter = EmbeddingFilter()
    
    assert filter.is_interesting("глупый вопрос") == True
    assert filter.is_interesting("++") == False
```

---

## Безопасность

### 1. Защита от злоупотреблений
- Владелец не может быть забанен
- PC команды ТОЛЬКО в личных сообщениях
- Опасные команды требуют подтверждения
- Rate limiting на API

### 2. Данные
- Хэширование чувствительной информации
- Регулярные бэкапы SQLite и Qdrant
- Логи не содержат токенов/ключей

### 3. Откаты
- Версионирование промптов
- Возможность отката к safe_mode
- Автоматический откат при критических ошибках

### 4. Мониторинг
- Алерты на аномалии (слишком много банов, крэши)
- Логи действий Ноти
- Возможность экстренного отключения

---

## Метрики успеха

### Технические
- [ ] Response time < 3 секунды
- [ ] Uptime > 99%
- [ ] Потребление API < 10к токенов/день
- [ ] Отклик на ~20% сообщений

### Поведенческие
- [ ] Помнит факты через неделю
- [ ] Адаптирует тон к пользователям
- [ ] Использует инструменты по ситуации
- [ ] Не ломается при странных запросах

### Качественные
- [ ] Реплики соответствуют характеру
- [ ] Непредсказуемость (не шаблонные ответы)
- [ ] Интересно читать мысленный монолог
- [ ] Владельцу нравится взаимодействие

---

## Риски и митигация

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| API ключи исчерпаны | Высокая | Мониторинг лимитов, уведомления |
| Ноти "сломалась" (неадекватное поведение) | Средняя | Откат промпта, safe_mode |
| Путаница между чатами | Средняя | Чёткое разделение контекстов |
| Потеря памяти при крэше | Низкая | Частые бэкапы, graceful shutdown |
| Злоупотребление инструментами | Низкая | Логирование, откат действий |
| Утечка данных | Низкая | Шифрование, ограниченный доступ |

---

## Дальнейшее развитие

### Идеи на будущее
1. **Голосовые сообщения** — Ноти может отвечать голосом
2. **Коллективная память** — несколько ботов учатся друг у друга
3. **Визуальный интерфейс** — веб-панель для управления
4. **Аналитика** — дашборд с метриками
5. **Интеграции** — календарь, заметки, напоминания
6. **Мультимодальность** — реакция на картинки

---

## Заключение

Проект **Ноти** — это не просто бот, а эксперимент по созданию AI-личности с:
- Характером и эмоциями
- Долговременной памятью
- Способностью учиться и эволюционировать
- Автономностью в управлении

Архитектура спроектирована с расчётом на:
- Расширяемость (новые инструменты, платформы)
- Надёжность (откаты, бэкапы, мониторинг)
- Прозрачность (логи, мысленный монолог)
- Экономичность (селективная реакция, ротация ключей)

**Следующий шаг**: Начать с Фазы 1 и итеративно двигаться к полной реализации.
