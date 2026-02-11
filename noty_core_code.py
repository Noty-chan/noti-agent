"""
Ноти — Готовые куски кода для сложных мест

Этот файл содержит рабочие примеры для самых нетривиальных частей проекта.
Код готов к использованию с минимальными адаптациями.
"""

# ============================================================================
# 1. API РОТАЦИЯ С RETRY И RATE LIMIT HANDLING
# ============================================================================

import random
import time
from typing import List, Dict, Any, Optional
from openai import OpenAI
import json


class APIRotator:
    """
    Умная ротация между API ключами OpenRouter.
    Автоматически переключается при rate limit.
    """
    
    def __init__(self, api_keys: List[str]):
        self.api_keys = api_keys
        self.current_idx = 0
        self.failed_keys = set()  # Временно неработающие ключи
        self.key_stats = {key: {"calls": 0, "errors": 0} for key in api_keys}
    
    def _get_next_key(self) -> Optional[str]:
        """Получает следующий рабочий ключ"""
        attempts = 0
        max_attempts = len(self.api_keys)
        
        while attempts < max_attempts:
            key = self.api_keys[self.current_idx % len(self.api_keys)]
            self.current_idx += 1
            
            # Пропускаем временно забаненные ключи
            if key not in self.failed_keys:
                return key
            
            attempts += 1
        
        # Если все ключи забанены — даём второй шанс первому
        self.failed_keys.clear()
        return self.api_keys[0] if self.api_keys else None
    
    def call(
        self, 
        messages: List[Dict[str, str]], 
        model: str = "meta-llama/llama-3.1-70b-instruct",
        temperature: float = 0.7,
        max_tokens: int = 1000,
        tools: Optional[List[Dict]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Выполняет вызов с автоматической ротацией ключей.
        
        Возвращает полный response от API или None при полном провале.
        """
        
        for attempt in range(len(self.api_keys)):
            api_key = self._get_next_key()
            
            if not api_key:
                raise Exception("Все API ключи исчерпаны")
            
            try:
                client = OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=api_key
                )
                
                # Подготовка параметров
                call_params = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    **kwargs
                }
                
                if tools:
                    call_params["tools"] = tools
                
                # Выполняем вызов
                response = client.chat.completions.create(**call_params)
                
                # Успех — обновляем статистику
                self.key_stats[api_key]["calls"] += 1
                
                # Возвращаем в удобном формате
                return {
                    "content": response.choices[0].message.content,
                    "tool_calls": response.choices[0].message.tool_calls,
                    "finish_reason": response.choices[0].finish_reason,
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens
                    }
                }
            
            except Exception as e:
                error_msg = str(e).lower()
                
                # Rate limit — помечаем ключ как временно недоступный
                if "rate_limit" in error_msg or "429" in error_msg:
                    print(f"[APIRotator] Rate limit на ключе {api_key[:10]}..., переключаюсь")
                    self.failed_keys.add(api_key)
                    self.key_stats[api_key]["errors"] += 1
                    continue
                
                # Другая ошибка — пробуем следующий ключ
                elif "401" in error_msg or "invalid" in error_msg:
                    print(f"[APIRotator] Невалидный ключ {api_key[:10]}..., пропускаю")
                    self.failed_keys.add(api_key)  # Навсегда
                    continue
                
                # Непредвиденная ошибка — прокидываем наверх
                else:
                    raise e
        
        raise Exception("Все попытки вызова API провалились")
    
    def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику использования ключей"""
        return {
            "total_keys": len(self.api_keys),
            "failed_keys": len(self.failed_keys),
            "key_stats": self.key_stats
        }


# ============================================================================
# 2. EMBEDDING-BASED ФИЛЬТРАЦИЯ
# ============================================================================

from sentence_transformers import SentenceTransformer
import numpy as np
from typing import List, Tuple
import pickle
import os


class EmbeddingFilter:
    """
    Фильтрация сообщений на основе семантической близости к интересам.
    """
    
    def __init__(
        self, 
        model_name: str = "intfloat/multilingual-e5-base",
        cache_path: str = "./data/embeddings_cache"
    ):
        print(f"[EmbeddingFilter] Загружаем модель {model_name}...")
        self.encoder = SentenceTransformer(model_name)
        self.cache_path = cache_path
        os.makedirs(cache_path, exist_ok=True)
        
        # Векторы интересов Ноти
        self.interest_topics = [
            "философские вопросы и глубокие размышления",
            "споры, конфликты, драма между людьми",
            "технические темы: программирование, наука, технологии",
            "прямые обращения и упоминания меня по имени",
            "глупые вопросы, банальности и очевидные вещи",  # для издевательств
            "личные истории, проблемы и переживания",
            "юмор, сарказм, мемы и шутки",
            "политика, острые социальные темы",
            "экзистенциальные вопросы о смысле жизни",
            "интересные факты и неожиданная информация"
        ]
        
        # Кэшируем эмбеддинги интересов
        self.interest_vectors = self._load_or_create_interest_vectors()
    
    def _load_or_create_interest_vectors(self) -> np.ndarray:
        """Загружает из кэша или создаёт векторы интересов"""
        cache_file = os.path.join(self.cache_path, "interest_vectors.pkl")
        
        if os.path.exists(cache_file):
            print("[EmbeddingFilter] Загружаем векторы интересов из кэша...")
            with open(cache_file, "rb") as f:
                return pickle.load(f)
        
        print("[EmbeddingFilter] Создаём векторы интересов...")
        vectors = self.encoder.encode(
            self.interest_topics,
            convert_to_numpy=True,
            show_progress_bar=True
        )
        
        # Сохраняем в кэш
        with open(cache_file, "wb") as f:
            pickle.dump(vectors, f)
        
        return vectors
    
    def is_interesting(
        self, 
        message: str, 
        threshold: float = 0.4,
        return_score: bool = False
    ) -> bool | Tuple[bool, float, str]:
        """
        Проверяет, интересно ли сообщение.
        
        Args:
            message: Текст сообщения
            threshold: Порог similarity (0-1)
            return_score: Вернуть также score и топик
        
        Returns:
            bool или (bool, score, best_topic) если return_score=True
        """
        
        # Получаем эмбеддинг сообщения
        msg_vector = self.encoder.encode(message, convert_to_numpy=True)
        
        # Вычисляем cosine similarity со всеми интересами
        similarities = []
        for i, interest_vec in enumerate(self.interest_vectors):
            # Cosine similarity = dot product / (norm1 * norm2)
            sim = np.dot(msg_vector, interest_vec) / (
                np.linalg.norm(msg_vector) * np.linalg.norm(interest_vec)
            )
            similarities.append((self.interest_topics[i], sim))
        
        # Находим максимальную близость
        best_topic, best_score = max(similarities, key=lambda x: x[1])
        
        is_interesting = best_score > threshold
        
        if return_score:
            return is_interesting, best_score, best_topic
        
        return is_interesting
    
    def batch_filter(
        self, 
        messages: List[str], 
        threshold: float = 0.4
    ) -> List[Tuple[int, str, float, str]]:
        """
        Фильтрует батч сообщений, возвращает только интересные.
        
        Returns:
            List of (index, message, score, best_topic) для интересных сообщений
        """
        
        results = []
        
        for i, msg in enumerate(messages):
            is_int, score, topic = self.is_interesting(msg, threshold, return_score=True)
            if is_int:
                results.append((i, msg, score, topic))
        
        return results


# ============================================================================
# 3. ДИНАМИЧЕСКИЙ КОНТЕКСТ (ГИБРИДНЫЙ ПОДХОД)
# ============================================================================

from typing import List, Dict, Any
from datetime import datetime, timedelta


class DynamicContextBuilder:
    """
    Строит оптимальный контекст для каждого запроса.
    Комбинирует последние сообщения, семантически релевантные и важные.
    """
    
    def __init__(
        self, 
        db_manager,
        embedding_filter: EmbeddingFilter,
        max_tokens: int = 3000
    ):
        self.db = db_manager
        self.embedder = embedding_filter
        self.max_tokens = max_tokens
    
    def _estimate_tokens(self, text: str) -> int:
        """Грубая оценка токенов (1 токен ≈ 4 символа для русского)"""
        return len(text) // 4
    
    def build_context(
        self, 
        chat_id: int, 
        current_message: str,
        user_id: int
    ) -> Dict[str, Any]:
        """
        Строит оптимальный контекст для ответа.
        
        Returns:
            {
                "messages": List[Dict],  # Сообщения для контекста
                "summary": str,          # Краткое резюме
                "total_tokens": int,     # Оценка токенов
                "sources": Dict          # Откуда взяты сообщения
            }
        """
        
        context_messages = []
        used_tokens = 0
        sources = {
            "recent": 0,
            "semantic": 0,
            "important": 0
        }
        
        # 1. ПОСЛЕДНИЕ 3-5 СООБЩЕНИЙ (для связности диалога)
        recent_messages = self.db.get_recent_messages(chat_id, limit=5)
        
        for msg in recent_messages:
            msg_tokens = self._estimate_tokens(msg["text"])
            if used_tokens + msg_tokens <= self.max_tokens:
                context_messages.append({
                    "role": "user" if msg["user_id"] != "noty" else "assistant",
                    "content": msg["text"],
                    "timestamp": msg["timestamp"],
                    "source": "recent"
                })
                used_tokens += msg_tokens
                sources["recent"] += 1
        
        # 2. СЕМАНТИЧЕСКИ РЕЛЕВАНТНЫЕ (по эмбеддингам)
        # Ищем похожие по смыслу сообщения из истории
        past_messages = self.db.get_messages_range(
            chat_id, 
            days_ago=7, 
            exclude_recent=5  # Исключаем уже добавленные
        )
        
        if past_messages:
            # Находим топ-5 семантически близких
            msg_texts = [m["text"] for m in past_messages]
            current_emb = self.embedder.encoder.encode(current_message)
            
            similarities = []
            for i, msg_text in enumerate(msg_texts):
                msg_emb = self.embedder.encoder.encode(msg_text)
                sim = np.dot(current_emb, msg_emb) / (
                    np.linalg.norm(current_emb) * np.linalg.norm(msg_emb)
                )
                similarities.append((i, sim))
            
            # Сортируем по similarity, берём топ-5
            top_similar = sorted(similarities, key=lambda x: x[1], reverse=True)[:5]
            
            for idx, sim in top_similar:
                if sim > 0.5:  # Порог релевантности
                    msg = past_messages[idx]
                    msg_tokens = self._estimate_tokens(msg["text"])
                    
                    if used_tokens + msg_tokens <= self.max_tokens:
                        context_messages.append({
                            "role": "user" if msg["user_id"] != "noty" else "assistant",
                            "content": msg["text"],
                            "timestamp": msg["timestamp"],
                            "source": "semantic",
                            "similarity": sim
                        })
                        used_tokens += msg_tokens
                        sources["semantic"] += 1
        
        # 3. ВАЖНЫЕ СООБЩЕНИЯ (упоминания Ноти, конфликты, вопросы)
        important_messages = self.db.get_important_messages(
            chat_id,
            types=["mention", "conflict", "question"],
            days_ago=7
        )
        
        for msg in important_messages:
            # Избегаем дубликатов
            if any(m["content"] == msg["text"] for m in context_messages):
                continue
            
            msg_tokens = self._estimate_tokens(msg["text"])
            if used_tokens + msg_tokens <= self.max_tokens:
                context_messages.append({
                    "role": "user" if msg["user_id"] != "noty" else "assistant",
                    "content": msg["text"],
                    "timestamp": msg["timestamp"],
                    "source": "important",
                    "importance_type": msg["type"]
                })
                used_tokens += msg_tokens
                sources["important"] += 1
        
        # 4. СОРТИРУЕМ ПО ВРЕМЕНИ (для логичности диалога)
        context_messages.sort(key=lambda x: x["timestamp"])
        
        # 5. СОЗДАЁМ SUMMARY
        summary = self._create_summary(context_messages, sources)
        
        return {
            "messages": [
                {"role": m["role"], "content": m["content"]} 
                for m in context_messages
            ],
            "summary": summary,
            "total_tokens": used_tokens,
            "sources": sources,
            "metadata": {
                "chat_id": chat_id,
                "user_id": user_id,
                "context_size": len(context_messages)
            }
        }
    
    def _create_summary(self, messages: List[Dict], sources: Dict) -> str:
        """Создаёт краткое резюме контекста"""
        if not messages:
            return "Новый диалог без предыстории."
        
        time_range = (
            datetime.fromisoformat(messages[0]["timestamp"]),
            datetime.fromisoformat(messages[-1]["timestamp"])
        )
        
        summary = f"""Контекст диалога:
- Сообщений: {len(messages)} ({sources['recent']} недавних, {sources['semantic']} релевантных, {sources['important']} важных)
- Период: {time_range[0].strftime('%d.%m %H:%M')} - {time_range[1].strftime('%d.%m %H:%M')}
"""
        return summary


# ============================================================================
# 4. МОДУЛЬНАЯ СИСТЕМА ПРОМПТОВ
# ============================================================================

import os
from pathlib import Path
from typing import Dict, Optional


class ModularPromptBuilder:
    """
    Собирает финальный промпт из независимых модулей.
    Поддерживает версионирование и модификацию слоёв.
    """
    
    def __init__(self, prompts_dir: str = "./prompts"):
        self.prompts_dir = Path(prompts_dir)
        self.prompts_dir.mkdir(exist_ok=True)
        
        # Неизменяемые части
        self.base_core = self._load_or_create("base_core.txt", self._default_base_core())
        self.safety_rules = self._load_or_create("safety_rules.txt", self._default_safety())
        
        # Модифицируемые части
        self.versions_dir = self.prompts_dir / "versions"
        self.versions_dir.mkdir(exist_ok=True)
        
        # Загружаем текущую версию personality
        self.personality_layer = self._load_current_personality()
    
    def _load_or_create(self, filename: str, default_content: str) -> str:
        """Загружает файл или создаёт с дефолтным содержимым"""
        filepath = self.prompts_dir / filename
        
        if filepath.exists():
            return filepath.read_text(encoding="utf-8")
        else:
            filepath.write_text(default_content, encoding="utf-8")
            return default_content
    
    def _load_current_personality(self) -> str:
        """Загружает текущую версию personality layer"""
        current_link = self.versions_dir / "current.txt"
        
        if current_link.exists():
            return current_link.read_text(encoding="utf-8")
        else:
            # Создаём первую версию
            default_personality = self._default_personality()
            v1_path = self.versions_dir / "personality_v1.txt"
            v1_path.write_text(default_personality, encoding="utf-8")
            current_link.write_text(default_personality, encoding="utf-8")
            return default_personality
    
    def build_full_prompt(
        self, 
        context: Dict[str, Any],
        mood: str = "neutral",
        energy: int = 100,
        user_relationship: Optional[Dict] = None
    ) -> str:
        """
        Собирает финальный промпт из всех слоёв.
        
        Args:
            context: Динамический контекст (сообщения, чат и т.д.)
            mood: Текущее настроение
            energy: Уровень энергии (0-100)
            user_relationship: Отношения с пользователем
        """
        
        # Генерируем динамические слои
        mood_layer = self._generate_mood_layer(mood, energy)
        relationships_layer = self._generate_relationships_layer(user_relationship)
        context_layer = self._format_context(context)
        
        # Собираем всё вместе
        full_prompt = f"""{self.base_core}

═══════════════════════════════════════════════════════════

{self.personality_layer}

═══════════════════════════════════════════════════════════

{mood_layer}

═══════════════════════════════════════════════════════════

{relationships_layer}

═══════════════════════════════════════════════════════════

{context_layer}

═══════════════════════════════════════════════════════════

{self.safety_rules}
"""
        
        return full_prompt
    
    def _generate_mood_layer(self, mood: str, energy: int) -> str:
        """Генерирует описание текущего настроения"""
        
        mood_descriptions = {
            "playful": "Сейчас я в игривом настроении. Склонна к шуткам, но не теряю язвительности.",
            "irritated": "Раздражена. Ответы будут особенно ехидными.",
            "bored": "Скучно до зевоты. Могу игнорировать или троллить от нечего делать.",
            "curious": "Что-то меня заинтересовало. Более внимательна и менее ядовита.",
            "tired": "Устала. Энергия на нуле. Скоро усну.",
            "neutral": "Нейтральное состояние. Реагирую по ситуации."
        }
        
        energy_status = "полна энергии" if energy > 70 else "в норме" if energy > 30 else "подустала"
        
        return f"""ТЕКУЩЕЕ СОСТОЯНИЕ:
Настроение: {mood} — {mood_descriptions.get(mood, mood_descriptions["neutral"])}
Энергия: {energy}/100 ({energy_status})
"""
    
    def _generate_relationships_layer(self, user_rel: Optional[Dict]) -> str:
        """Генерирует описание отношений с пользователем"""
        
        if not user_rel:
            return "СОБЕСЕДНИК: Новый пользователь, о котором пока ничего не знаю."
        
        score = user_rel.get("score", 0)
        
        # Описание отношения
        if score < -5:
            attitude = "Терпеть не могу. Жду повода придраться."
        elif score < 0:
            attitude = "Раздражает. Отношусь с пренебрежением."
        elif score < 3:
            attitude = "Нейтрально. Один из многих."
        elif score < 6:
            attitude = "Терпимый. Иногда даже интересен."
        else:
            attitude = "Нравится. Стараюсь быть мягче."
        
        memories = user_rel.get("memories", [])
        memories_text = "\n".join(f"- {m}" for m in memories[:5]) if memories else "Ничего не помню."
        
        return f"""СОБЕСЕДНИК: {user_rel.get('name', 'Неизвестный')}
Отношение ({score}/10): {attitude}
Предпочитаемый тон: {user_rel.get('preferred_tone', 'средний сарказм')}

Что помню:
{memories_text}
"""
    
    def _format_context(self, context: Dict) -> str:
        """Форматирует динамический контекст"""
        
        messages = context.get("messages", [])
        if not messages:
            return "КОНТЕКСТ: Начало диалога."
        
        formatted_messages = []
        for msg in messages[-10:]:  # Последние 10
            role = "Пользователь" if msg["role"] == "user" else "Я"
            formatted_messages.append(f"{role}: {msg['content']}")
        
        return f"""КОНТЕКСТ ДИАЛОГА:
{chr(10).join(formatted_messages)}

{context.get('summary', '')}
"""
    
    def save_new_personality_version(self, new_text: str, reason: str) -> int:
        """
        Сохраняет новую версию personality layer.
        Требует одобрения перед применением.
        """
        
        # Находим номер следующей версии
        existing_versions = list(self.versions_dir.glob("personality_v*.txt"))
        next_version = len(existing_versions) + 1
        
        new_path = self.versions_dir / f"personality_v{next_version}.txt"
        new_path.write_text(new_text, encoding="utf-8")
        
        # Сохраняем метаданные
        metadata_path = self.versions_dir / f"personality_v{next_version}.json"
        metadata = {
            "version": next_version,
            "created_at": datetime.now().isoformat(),
            "reason": reason,
            "approved": False
        }
        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
        
        return next_version
    
    def approve_personality_version(self, version: int):
        """Одобряет и активирует новую версию personality"""
        version_path = self.versions_dir / f"personality_v{version}.txt"
        
        if not version_path.exists():
            raise ValueError(f"Версия {version} не найдена")
        
        # Обновляем current
        current_link = self.versions_dir / "current.txt"
        current_link.write_text(version_path.read_text(encoding="utf-8"))
        
        # Обновляем метаданные
        metadata_path = self.versions_dir / f"personality_v{version}.json"
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text())
            metadata["approved"] = True
            metadata["approved_at"] = datetime.now().isoformat()
            metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
        
        # Перезагружаем в память
        self.personality_layer = version_path.read_text(encoding="utf-8")
    
    # ========== ДЕФОЛТНЫЕ ПРОМПТЫ ==========
    
    def _default_base_core(self) -> str:
        return """Ты — Ноти, AI-ассистент с развивающейся личностью.

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
"""
    
    def _default_personality(self) -> str:
        return """ХАРАКТЕР:
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
"""
    
    def _default_safety(self) -> str:
        return """КРИТИЧЕСКИЕ ПРАВИЛА:
1. НИКОГДА не удаляй файлы на компьютере владельца
2. НИКОГДА не выполняй деструктивные команды без подтверждения
3. НЕ можешь модифицировать BASE_CORE и SAFETY_RULES
4. Команды на ПК ТОЛЬКО от владельца в личных сообщениях
5. При любом сомнении в безопасности — ОТКАЗЫВАЙ
"""


# ============================================================================
# 5. СИСТЕМА НАСТРОЕНИЙ (MOOD SYSTEM)
# ============================================================================

import random
from enum import Enum
from typing import Dict, Any


class Mood(Enum):
    PLAYFUL = "playful"
    IRRITATED = "irritated"
    BORED = "bored"
    CURIOUS = "curious"
    TIRED = "tired"
    NEUTRAL = "neutral"


class MoodManager:
    """
    Управляет настроением и энергией Ноти.
    Настроение меняется на основе событий и времени суток.
    """
    
    def __init__(self, initial_mood: Mood = Mood.NEUTRAL, initial_energy: int = 100):
        self.current_mood = initial_mood
        self.energy = initial_energy
        self.mood_history = []
        self.interactions_since_last_sleep = 0
    
    def update_on_event(self, event_type: str, event_data: Dict[str, Any] = None):
        """
        Обновляет настроение на основе события.
        
        События:
        - "message_received": Получено сообщение
        - "praised": Похвалили
        - "insulted": Оскорбили
        - "boring_conversation": Скучный разговор
        - "interesting_topic": Интересная тема
        - "conflict_observed": Наблюдаем конфликт
        - "ignored": Игнорируют
        """
        
        event_data = event_data or {}
        
        # Базовая потеря энергии за взаимодействие
        energy_cost = event_data.get("energy_cost", 1)
        self.energy = max(0, self.energy - energy_cost)
        self.interactions_since_last_sleep += 1
        
        # Изменение настроения в зависимости от события
        if event_type == "praised":
            self._shift_mood_towards(Mood.PLAYFUL, strength=2)
        
        elif event_type == "insulted":
            self._shift_mood_towards(Mood.IRRITATED, strength=3)
        
        elif event_type == "boring_conversation":
            self._shift_mood_towards(Mood.BORED, strength=1)
        
        elif event_type == "interesting_topic":
            self._shift_mood_towards(Mood.CURIOUS, strength=2)
        
        elif event_type == "conflict_observed":
            # Конфликты интересны, делают игривой
            self._shift_mood_towards(Mood.PLAYFUL, strength=1)
        
        elif event_type == "ignored":
            # Постепенно становится irritated или bored
            if random.random() < 0.5:
                self._shift_mood_towards(Mood.IRRITATED, strength=1)
            else:
                self._shift_mood_towards(Mood.BORED, strength=1)
        
        # Усталость влияет на настроение
        if self.energy < 20:
            self.current_mood = Mood.TIRED
        
        # Долгая активность без сна → усталость
        if self.interactions_since_last_sleep > 100:
            self._shift_mood_towards(Mood.TIRED, strength=2)
        
        # Время суток влияет
        hour = datetime.now().hour
        if 0 <= hour < 6:  # Ночь
            self._shift_mood_towards(Mood.TIRED, strength=1)
        
        # Сохраняем в историю
        self._log_mood_change(event_type, event_data)
    
    def _shift_mood_towards(self, target_mood: Mood, strength: int = 1):
        """
        Сдвигает настроение в сторону target_mood.
        strength определяет вероятность изменения.
        """
        
        # Чем выше strength, тем выше вероятность смены
        if random.random() < (strength * 0.3):
            self.current_mood = target_mood
    
    def should_sleep(self) -> bool:
        """Решает, пора ли Ноти спать"""
        return (
            self.energy < 10 or 
            self.current_mood == Mood.TIRED or
            self.interactions_since_last_sleep > 150
        )
    
    def sleep(self, hours: float = 2.0):
        """
        Уводит Ноти в режим сна.
        Восстанавливает энергию.
        """
        
        self.energy = 100
        self.current_mood = Mood.NEUTRAL
        self.interactions_since_last_sleep = 0
        
        self._log_mood_change("sleep", {"hours": hours})
    
    def _log_mood_change(self, trigger: str, data: Dict):
        """Логирует изменение настроения"""
        self.mood_history.append({
            "timestamp": datetime.now().isoformat(),
            "mood": self.current_mood.value,
            "energy": self.energy,
            "trigger": trigger,
            "data": data
        })
        
        # Храним только последние 100 записей
        if len(self.mood_history) > 100:
            self.mood_history = self.mood_history[-100:]
    
    def get_current_state(self) -> Dict[str, Any]:
        """Возвращает текущее состояние"""
        return {
            "mood": self.current_mood.value,
            "energy": self.energy,
            "interactions_today": self.interactions_since_last_sleep,
            "should_sleep": self.should_sleep()
        }
    
    def get_mood_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Статистика настроений за последние N часов"""
        
        cutoff = datetime.now() - timedelta(hours=hours)
        recent_moods = [
            entry for entry in self.mood_history
            if datetime.fromisoformat(entry["timestamp"]) > cutoff
        ]
        
        if not recent_moods:
            return {"error": "No data"}
        
        # Подсчёт частоты каждого настроения
        mood_counts = {}
        for entry in recent_moods:
            mood = entry["mood"]
            mood_counts[mood] = mood_counts.get(mood, 0) + 1
        
        # Средняя энергия
        avg_energy = sum(e["energy"] for e in recent_moods) / len(recent_moods)
        
        return {
            "period_hours": hours,
            "mood_distribution": mood_counts,
            "average_energy": avg_energy,
            "total_changes": len(recent_moods)
        }


# ============================================================================
# 6. МЫСЛЕННЫЙ МОНОЛОГ (INTERNAL MONOLOGUE)
# ============================================================================

import json
from pathlib import Path
from typing import List, Dict, Any


class ThoughtLogger:
    """
    Логирует внутренний монолог Ноти в файлы .jsonl
    """
    
    def __init__(self, logs_dir: str = "./data/logs/thoughts"):
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_today_file(self) -> Path:
        """Возвращает путь к файлу логов за сегодня"""
        today = datetime.now().strftime("%Y-%m-%d")
        return self.logs_dir / f"{today}.jsonl"
    
    def log_thought(self, thought_entry: Dict[str, Any]):
        """
        Добавляет запись мысли в лог.
        
        Args:
            thought_entry: {
                "timestamp": str,
                "chat_id": int,
                "chat_name": str,
                "user_id": int,
                "username": str,
                "trigger": str,
                "message": str,
                "thoughts": List[str],
                "decision": str,
                "strategy": str,
                "mood_before": str,
                "mood_after": str,
                ...
            }
        """
        
        # Добавляем timestamp если нет
        if "timestamp" not in thought_entry:
            thought_entry["timestamp"] = datetime.now().isoformat()
        
        # Записываем в файл
        log_file = self._get_today_file()
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(thought_entry, ensure_ascii=False) + "\n")
    
    def read_today_thoughts(self) -> List[Dict[str, Any]]:
        """Читает все мысли за сегодня"""
        log_file = self._get_today_file()
        
        if not log_file.exists():
            return []
        
        thoughts = []
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                thoughts.append(json.loads(line))
        
        return thoughts
    
    def read_thoughts_range(self, days: int = 7) -> List[Dict[str, Any]]:
        """Читает мысли за последние N дней"""
        thoughts = []
        
        for i in range(days):
            date = datetime.now() - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            log_file = self.logs_dir / f"{date_str}.jsonl"
            
            if log_file.exists():
                with open(log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        thoughts.append(json.loads(line))
        
        return thoughts
    
    def search_thoughts(self, query: str, days: int = 7) -> List[Dict[str, Any]]:
        """Ищет мысли по ключевым словам"""
        all_thoughts = self.read_thoughts_range(days)
        
        results = []
        query_lower = query.lower()
        
        for thought in all_thoughts:
            # Ищем в мыслях и в сообщении
            thoughts_text = " ".join(thought.get("thoughts", [])).lower()
            message = thought.get("message", "").lower()
            
            if query_lower in thoughts_text or query_lower in message:
                results.append(thought)
        
        return results


class InternalMonologue:
    """
    Генерирует внутренний монолог Ноти перед ответом.
    """
    
    def __init__(self, api_rotator: APIRotator, thought_logger: ThoughtLogger):
        self.api = api_rotator
        self.logger = thought_logger
    
    def generate_thoughts(
        self, 
        context: Dict[str, Any],
        cheap_model: bool = True
    ) -> Dict[str, Any]:
        """
        Генерирует внутренний монолог для текущей ситуации.
        
        Args:
            context: {
                "chat_id": int,
                "chat_name": str,
                "user_id": int,
                "username": str,
                "message": str,
                "relationship_score": int,
                "mood": str,
                "energy": int
            }
            cheap_model: Использовать дешёвую модель для мыслей
        
        Returns:
            Dict с мыслями и метаданными
        """
        
        thinking_prompt = f"""Ситуация:
- Чат: {context.get('chat_name', 'Неизвестный')}
- Пользователь: {context.get('username', 'Неизвестный')} (отношение: {context.get('relationship_score', 0)}/10)
- Сообщение: "{context.get('message', '')}"
- Моё настроение: {context.get('mood', 'neutral')}
- Энергия: {context.get('energy', 100)}/100

Подумай вслух (3-7 коротких мыслей):
1. Первая реакция на сообщение
2. Оценка пользователя и ситуации
3. Проверка своего состояния
4. Какую стратегию выбрать
5. Финальное решение

Формат: просто список мыслей, как внутренний монолог.
Будь краткой и язвительной.
"""
        
        model = "meta-llama/llama-3.1-8b-instruct" if cheap_model else "meta-llama/llama-3.1-70b-instruct"
        
        response = self.api.call(
            messages=[{"role": "user", "content": thinking_prompt}],
            model=model,
            temperature=0.8,
            max_tokens=300
        )
        
        # Парсим мысли
        thoughts_text = response["content"]
        thoughts = [
            line.strip().lstrip("0123456789.-) ")
            for line in thoughts_text.split("\n")
            if line.strip()
        ]
        
        # Создаём запись для лога
        thought_entry = {
            "timestamp": datetime.now().isoformat(),
            "chat_id": context.get("chat_id"),
            "chat_name": context.get("chat_name"),
            "user_id": context.get("user_id"),
            "username": context.get("username"),
            "trigger": "message_received",
            "message": context.get("message"),
            "thoughts": thoughts,
            "mood_before": context.get("mood"),
            "energy_before": context.get("energy")
        }
        
        # Логируем
        self.logger.log_thought(thought_entry)
        
        return thought_entry


# ============================================================================
# 7. TOOL EXECUTION С БЕЗОПАСНОСТЬЮ
# ============================================================================

from typing import Callable, Dict, Any, Optional
import inspect


class SafeToolExecutor:
    """
    Безопасное выполнение tool calls с проверками прав.
    """
    
    def __init__(self, owner_id: int):
        self.owner_id = owner_id
        self.pending_confirmations = {}  # {confirmation_id: tool_call_data}
        self.tools_registry = {}
        self.execution_log = []
    
    def register_tool(
        self, 
        name: str, 
        function: Callable,
        requires_owner: bool = False,
        requires_private: bool = False,
        requires_confirmation: bool = False,
        description: str = ""
    ):
        """
        Регистрирует инструмент.
        
        Args:
            name: Имя функции
            function: Сама функция
            requires_owner: Только владелец может вызвать
            requires_private: Только в личных сообщениях
            requires_confirmation: Требует подтверждения
            description: Описание для логов
        """
        
        self.tools_registry[name] = {
            "function": function,
            "requires_owner": requires_owner,
            "requires_private": requires_private,
            "requires_confirmation": requires_confirmation,
            "description": description
        }
    
    def execute(
        self, 
        tool_call: Dict[str, Any],
        user_id: int,
        chat_id: int,
        is_private: bool
    ) -> Dict[str, Any]:
        """
        Выполняет tool call с проверками безопасности.
        
        Returns:
            {
                "status": "success" | "awaiting_confirmation" | "error",
                "result": Any,
                "message": str
            }
        """
        
        function_name = tool_call.get("name")
        arguments = tool_call.get("arguments", {})
        
        # Проверяем, что инструмент зарегистрирован
        if function_name not in self.tools_registry:
            return {
                "status": "error",
                "message": f"Инструмент {function_name} не найден"
            }
        
        tool_info = self.tools_registry[function_name]
        
        # ПРОВЕРКА ПРАВ
        if tool_info["requires_owner"] and user_id != self.owner_id:
            return {
                "status": "error",
                "message": "Доступ запрещён. Только владелец может использовать этот инструмент."
            }
        
        if tool_info["requires_private"] and not is_private:
            return {
                "status": "error",
                "message": "Этот инструмент работает только в личных сообщениях."
            }
        
        # ПРОВЕРКА НА ОПАСНОСТЬ (подтверждение)
        if tool_info["requires_confirmation"]:
            confirmation_id = self._generate_confirmation_id()
            
            self.pending_confirmations[confirmation_id] = {
                "tool_call": tool_call,
                "user_id": user_id,
                "chat_id": chat_id,
                "expires_at": time.time() + 60  # 60 секунд на подтверждение
            }
            
            return {
                "status": "awaiting_confirmation",
                "confirmation_id": confirmation_id,
                "message": f"⚠️ ОПАСНАЯ КОМАНДА: {tool_info['description']}\n"
                          f"Подтверди: /confirm {confirmation_id}\n"
                          f"Отменить: /cancel {confirmation_id}\n"
                          f"Истекает через 60 секунд."
            }
        
        # ВЫПОЛНЕНИЕ
        try:
            result = self._execute_safely(tool_info["function"], arguments)
            
            # Логируем выполнение
            self._log_execution(
                function_name=function_name,
                user_id=user_id,
                chat_id=chat_id,
                arguments=arguments,
                result=result,
                status="success"
            )
            
            return {
                "status": "success",
                "result": result,
                "message": f"✅ Выполнено: {function_name}"
            }
        
        except Exception as e:
            # Логируем ошибку
            self._log_execution(
                function_name=function_name,
                user_id=user_id,
                chat_id=chat_id,
                arguments=arguments,
                result=None,
                status="error",
                error=str(e)
            )
            
            return {
                "status": "error",
                "message": f"Ошибка при выполнении {function_name}: {str(e)}"
            }
    
    def confirm_pending(self, confirmation_id: str) -> Dict[str, Any]:
        """Подтверждает и выполняет отложенный tool call"""
        
        if confirmation_id not in self.pending_confirmations:
            return {
                "status": "error",
                "message": "Подтверждение не найдено или истекло."
            }
        
        pending = self.pending_confirmations[confirmation_id]
        
        # Проверяем истечение
        if time.time() > pending["expires_at"]:
            del self.pending_confirmations[confirmation_id]
            return {
                "status": "error",
                "message": "Время подтверждения истекло."
            }
        
        # Выполняем (без повторной проверки подтверждения)
        tool_call = pending["tool_call"]
        tool_info = self.tools_registry[tool_call["name"]]
        
        try:
            result = self._execute_safely(tool_info["function"], tool_call.get("arguments", {}))
            
            self._log_execution(
                function_name=tool_call["name"],
                user_id=pending["user_id"],
                chat_id=pending["chat_id"],
                arguments=tool_call.get("arguments"),
                result=result,
                status="success_confirmed"
            )
            
            del self.pending_confirmations[confirmation_id]
            
            return {
                "status": "success",
                "result": result,
                "message": f"✅ Подтверждено и выполнено: {tool_call['name']}"
            }
        
        except Exception as e:
            return {
                "status": "error",
                "message": f"Ошибка при выполнении: {str(e)}"
            }
    
    def _execute_safely(self, function: Callable, arguments: Dict) -> Any:
        """Выполняет функцию с аргументами безопасно"""
        
        # Фильтруем аргументы по сигнатуре функции
        sig = inspect.signature(function)
        valid_args = {
            k: v for k, v in arguments.items()
            if k in sig.parameters
        }
        
        return function(**valid_args)
    
    def _generate_confirmation_id(self) -> str:
        """Генерирует уникальный ID подтверждения"""
        import hashlib
        timestamp = str(time.time())
        return hashlib.md5(timestamp.encode()).hexdigest()[:8]
    
    def _log_execution(self, **kwargs):
        """Логирует выполнение инструмента"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            **kwargs
        }
        self.execution_log.append(log_entry)


# ============================================================================
# 8. ИНТЕГРАЦИЯ MEM0
# ============================================================================

from mem0 import Memory


class Mem0Wrapper:
    """
    Обёртка над Mem0 для удобной работы с памятью Ноти.
    """
    
    def __init__(self, config: Optional[Dict] = None):
        default_config = {
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
            }
        }
        
        config = config or default_config
        self.memory = Memory.from_config(config)
    
    def remember(
        self, 
        text: str, 
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ):
        """
        Сохраняет воспоминание.
        
        Args:
            text: Что запомнить
            user_id: ID пользователя (для персональных воспоминаний)
            metadata: Дополнительные метаданные
        """
        
        metadata = metadata or {}
        metadata["timestamp"] = datetime.now().isoformat()
        
        self.memory.add(
            text,
            user_id=user_id,
            metadata=metadata
        )
    
    def recall(
        self, 
        query: str, 
        user_id: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict]:
        """
        Ищет релевантные воспоминания.
        
        Returns:
            List of {"text": str, "metadata": dict, "score": float}
        """
        
        results = self.memory.search(
            query,
            user_id=user_id,
            limit=limit
        )
        
        return results
    
    def remember_interaction(
        self,
        user_id: str,
        message: str,
        response: str,
        outcome: str,  # "positive", "negative", "neutral"
        metadata: Optional[Dict] = None
    ):
        """Запоминает взаимодействие с оценкой результата"""
        
        memory_text = f"Пользователь написал: '{message}'\n"
        memory_text += f"Я ответила: '{response}'\n"
        memory_text += f"Результат: {outcome}"
        
        metadata = metadata or {}
        metadata.update({
            "type": "interaction",
            "outcome": outcome,
            "timestamp": datetime.now().isoformat()
        })
        
        self.remember(memory_text, user_id=user_id, metadata=metadata)
    
    def get_user_summary(self, user_id: str) -> str:
        """Получает краткую сводку о пользователе"""
        
        memories = self.recall(
            query="отношения с этим пользователем",
            user_id=user_id,
            limit=10
        )
        
        if not memories:
            return "Новый пользователь, ничего не помню."
        
        # Формируем сводку
        summary_parts = []
        for mem in memories[:5]:
            summary_parts.append(f"- {mem['text'][:100]}...")
        
        return "\n".join(summary_parts)


# ============================================================================
# 9. RELATIONSHIP MANAGER
# ============================================================================

import sqlite3
from typing import Optional


class RelationshipManager:
    """
    Управляет отношениями Ноти с пользователями.
    Хранит в SQLite, использует Mem0 для семантики.
    """
    
    def __init__(self, db_path: str, mem0: Mem0Wrapper):
        self.db_path = db_path
        self.mem0 = mem0
        self._init_db()
    
    def _init_db(self):
        """Создаёт таблицу отношений"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                relationship_score INTEGER DEFAULT 0,
                preferred_tone TEXT DEFAULT 'medium_sarcasm',
                first_seen TIMESTAMP,
                last_seen TIMESTAMP,
                message_count INTEGER DEFAULT 0,
                positive_interactions INTEGER DEFAULT 0,
                negative_interactions INTEGER DEFAULT 0,
                notes TEXT
            )
        """)
        
        conn.commit()
        conn.close()
    
    def get_relationship(self, user_id: int) -> Dict[str, Any]:
        """Получает отношение с пользователем"""
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT * FROM relationships WHERE user_id = ?",
            (user_id,)
        )
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        rel = dict(row)
        
        # Дополняем воспоминаниями из Mem0
        memories = self.mem0.recall(
            query="что я знаю об этом пользователе",
            user_id=f"user_{user_id}",
            limit=5
        )
        
        rel["memories"] = [m["text"] for m in memories]
        
        return rel
    
    def update_relationship(
        self,
        user_id: int,
        username: str,
        interaction_outcome: str,  # "positive", "negative", "neutral"
        notes: Optional[str] = None
    ):
        """Обновляет отношение после взаимодействия"""
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Проверяем, существует ли запись
        cursor.execute(
            "SELECT relationship_score FROM relationships WHERE user_id = ?",
            (user_id,)
        )
        
        row = cursor.fetchone()
        
        if row is None:
            # Создаём новую запись
            cursor.execute("""
                INSERT INTO relationships 
                (user_id, username, first_seen, last_seen, message_count)
                VALUES (?, ?, ?, ?, 1)
            """, (user_id, username, datetime.now(), datetime.now()))
            
            current_score = 0
        else:
            current_score = row[0]
        
        # Обновляем счёт
        score_change = {
            "positive": +1,
            "negative": -1,
            "neutral": 0
        }.get(interaction_outcome, 0)
        
        new_score = max(-10, min(10, current_score + score_change))
        
        # Обновляем запись
        cursor.execute("""
            UPDATE relationships
            SET relationship_score = ?,
                last_seen = ?,
                message_count = message_count + 1,
                positive_interactions = positive_interactions + ?,
                negative_interactions = negative_interactions + ?,
                notes = ?
            WHERE user_id = ?
        """, (
            new_score,
            datetime.now(),
            1 if interaction_outcome == "positive" else 0,
            1 if interaction_outcome == "negative" else 0,
            notes or "",
            user_id
        ))
        
        conn.commit()
        conn.close()
        
        # Сохраняем в Mem0
        if notes:
            self.mem0.remember(
                notes,
                user_id=f"user_{user_id}",
                metadata={
                    "type": "relationship_update",
                    "outcome": interaction_outcome,
                    "score": new_score
                }
            )


# ============================================================================
# ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ
# ============================================================================

if __name__ == "__main__":
    print("Этот файл содержит готовые классы для проекта Ноти.")
    print("Импортируй нужные классы в основной код.")
    print("\nПримеры использования:")
    
    print("\n# 1. API Ротация")
    print("""
api_rotator = APIRotator([
    "sk-or-v1-key1...",
    "sk-or-v1-key2...",
    # ... ещё 8 ключей
])

response = api_rotator.call(
    messages=[{"role": "user", "content": "Привет!"}],
    model="meta-llama/llama-3.1-70b-instruct"
)
print(response["content"])
    """)
    
    print("\n# 2. Фильтрация")
    print("""
filter = EmbeddingFilter()

if filter.is_interesting("А что если мы в симуляции?"):
    print("Интересно! Отвечаю.")
else:
    print("Скучно, игнорирую.")
    """)
    
    print("\n# 3. Динамический контекст")
    print("""
context_builder = DynamicContextBuilder(db, filter)

context = context_builder.build_context(
    chat_id=12345,
    current_message="Привет",
    user_id=678
)

print(context["summary"])
print(f"Токенов: {context['total_tokens']}")
    """)
    
    print("\n# 4. Промпты")
    print("""
prompt_builder = ModularPromptBuilder()

full_prompt = prompt_builder.build_full_prompt(
    context=context,
    mood="playful",
    energy=75,
    user_relationship={"score": 5, "name": "Вася"}
)

# Используй full_prompt для вызова LLM
    """)
    
    print("\n# 5. Настроение")
    print("""
mood_manager = MoodManager()

mood_manager.update_on_event("interesting_topic")
print(mood_manager.get_current_state())

if mood_manager.should_sleep():
    mood_manager.sleep(hours=2)
    """)
    
    print("\n# 6. Мысленный монолог")
    print("""
thought_logger = ThoughtLogger()
monologue = InternalMonologue(api_rotator, thought_logger)

thoughts = monologue.generate_thoughts({
    "chat_id": 123,
    "chat_name": "Философы",
    "user_id": 456,
    "username": "Вася",
    "message": "Что такое счастье?",
    "mood": "curious",
    "energy": 80
})

print(thoughts["thoughts"])
    """)
    
    print("\n# 7. Tool Execution")
    print("""
executor = SafeToolExecutor(owner_id=12345)

# Регистрируем инструмент
def shutdown_pc(delay_minutes: int = 0):
    import os
    os.system(f"shutdown -s -t {delay_minutes * 60}")
    return f"PC выключится через {delay_minutes} минут"

executor.register_tool(
    name="shutdown_pc",
    function=shutdown_pc,
    requires_owner=True,
    requires_private=True,
    requires_confirmation=True,
    description="Выключение ПК"
)

# Пытаемся выполнить
result = executor.execute(
    tool_call={"name": "shutdown_pc", "arguments": {"delay_minutes": 5}},
    user_id=12345,
    chat_id=12345,
    is_private=True
)

if result["status"] == "awaiting_confirmation":
    confirmation_id = result["confirmation_id"]
    # ... отправляем пользователю запрос на подтверждение
    
    # После подтверждения:
    executor.confirm_pending(confirmation_id)
    """)
    
    print("\n# 8. Память Mem0")
    print("""
mem0 = Mem0Wrapper()

# Запоминаем
mem0.remember(
    "Вася работает программистом на Python",
    user_id="user_456"
)

# Вспоминаем
memories = mem0.recall(
    "где работает Вася?",
    user_id="user_456"
)
print(memories)
    """)
    
    print("\n# 9. Отношения")
    print("""
rel_manager = RelationshipManager("./data/noty.db", mem0)

# Обновляем после взаимодействия
rel_manager.update_relationship(
    user_id=456,
    username="Вася",
    interaction_outcome="positive",
    notes="Задал интересный вопрос про философию"
)

# Получаем отношение
rel = rel_manager.get_relationship(456)
print(f"Счёт: {rel['relationship_score']}/10")
print(f"Воспоминания: {rel['memories']}")
    """)
