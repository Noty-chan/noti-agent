"""Гибридный сборщик контекста: recent + semantic + important."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any, Dict, List

import numpy as np

from noty.filters.embedding_filter import EmbeddingFilter
from noty.memory.recent_days_memory import RecentDaysMemory
from noty.utils.metrics import MetricsCollector


class DynamicContextBuilder:
    def __init__(
        self,
        db_manager: Any,
        embedding_filter: EmbeddingFilter,
        max_tokens: int = 3000,
        semantic_retriever: Any | None = None,
        recent_days_memory: RecentDaysMemory | None = None,
        metrics: MetricsCollector | None = None,
    ):
        self.db = db_manager
        self.embedder = embedding_filter
        self.max_tokens = max_tokens
        self.semantic_retriever = semantic_retriever
        self.recent_days_memory = recent_days_memory
        self.metrics = metrics
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return len(text) // 4

    @staticmethod
    def _db_call(method, platform: str, chat_id: int, **kwargs):
        try:
            return method(platform, chat_id, **kwargs)
        except TypeError:
            return method(chat_id, **kwargs)

    def build_context(
        self,
        chat_id: int,
        current_message: str,
        user_id: int,
        strategy_hints: Dict[str, Any] | None = None,
        platform: str = "unknown",
        persona_slice: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        context_messages: List[Dict[str, Any]] = []
        used_tokens = 0

        sources = {
            "notebook": 0,
            "recent": 0,
            "semantic": 0,
            "important": 0,
            "rolling_recent_days": 0,
        }

        hints = strategy_hints or {}
        notebook_limits = self.db.get_notebook_limits() if hasattr(self.db, "get_notebook_limits") else {}

        notebook_notes = self._db_call(getattr(self.db, "get_notebook_notes"), platform, chat_id, limit=5) if hasattr(self.db, "get_notebook_notes") else []
        for note in notebook_notes:
            note_text = f"[NOTE#{note['id']}] {note['note']}"
            note_tokens = self._estimate_tokens(note_text)
            if used_tokens + note_tokens <= self.max_tokens:
                context_messages.append(
                    {
                        "role": "assistant",
                        "content": note_text,
                        "timestamp": note["updated_at"],
                        "source": "notebook",
                    }
                )
                used_tokens += note_tokens
                sources["notebook"] += 1

        if self.recent_days_memory:
            self.recent_days_memory.remember_message(
                platform=platform,
                chat_id=chat_id,
                user_id=user_id,
                text=current_message,
            )
            maintenance_executed = self.recent_days_memory.run_maintenance_if_due()
            if maintenance_executed:
                self.logger.info("Rolling memory maintenance выполнен: platform=%s chat_id=%s", platform, chat_id)

        recent_messages = self._db_call(self.db.get_recent_messages, platform, chat_id, limit=5)
        for msg in recent_messages:
            msg_tokens = self._estimate_tokens(msg["text"])
            if used_tokens + msg_tokens <= self.max_tokens:
                context_messages.append(
                    {
                        "role": "user" if msg["user_id"] != "noty" else "assistant",
                        "content": msg["text"],
                        "timestamp": msg["timestamp"],
                        "source": "recent",
                    }
                )
                used_tokens += msg_tokens
                sources["recent"] += 1

        past_messages = self._db_call(self.db.get_messages_range, platform, chat_id, days_ago=7, exclude_recent=5)
        if past_messages:
            msg_texts = [m["text"] for m in past_messages]
            current_emb = self.embedder.encoder.encode(current_message)
            similarities = []
            for i, msg_text in enumerate(msg_texts):
                msg_emb = self.embedder.encoder.encode(msg_text)
                sim = np.dot(current_emb, msg_emb) / (np.linalg.norm(current_emb) * np.linalg.norm(msg_emb))
                similarities.append((i, sim))

            top_similar = sorted(similarities, key=lambda x: x[1], reverse=True)[:5]
            for idx, sim in top_similar:
                if sim > 0.5:
                    msg = past_messages[idx]
                    msg_tokens = self._estimate_tokens(msg["text"])
                    if used_tokens + msg_tokens <= self.max_tokens:
                        context_messages.append(
                            {
                                "role": "user" if msg["user_id"] != "noty" else "assistant",
                                "content": msg["text"],
                                "timestamp": msg["timestamp"],
                                "source": "semantic",
                                "similarity": float(sim),
                            }
                        )
                        used_tokens += msg_tokens
                        sources["semantic"] += 1

        important_messages = self._db_call(self.db.get_important_messages, platform, chat_id, days_ago=7)
        for msg in important_messages:
            if any(m["content"] == msg["text"] for m in context_messages):
                continue
            msg_tokens = self._estimate_tokens(msg["text"])
            if used_tokens + msg_tokens <= self.max_tokens:
                context_messages.append(
                    {
                        "role": "user" if msg["user_id"] != "noty" else "assistant",
                        "content": msg["text"],
                        "timestamp": msg["timestamp"],
                        "source": "important",
                        "importance_type": msg.get("type", "unknown"),
                    }
                )
                used_tokens += msg_tokens
                sources["important"] += 1

        if self.recent_days_memory:
            rolling_facts = self.recent_days_memory.get_context_facts(platform=platform, chat_id=chat_id, limit=4)
            for fact in rolling_facts:
                if any(m["content"] == fact["text"] for m in context_messages):
                    continue
                fact_tokens = self._estimate_tokens(fact["text"])
                if used_tokens + fact_tokens > self.max_tokens:
                    continue
                context_messages.append(
                    {
                        "role": "assistant",
                        "content": fact["text"],
                        "timestamp": fact["created_at"],
                        "source": "rolling_recent_days",
                        "weight": round(float(fact["weight"]), 4),
                    }
                )
                used_tokens += fact_tokens
                sources["rolling_recent_days"] += 1

        conflict_topics = [t.lower() for t in hints.get("avoid_topics", [])]
        if conflict_topics:
            context_messages = [m for m in context_messages if not any(topic in m["content"].lower() for topic in conflict_topics)]

        if self.semantic_retriever:
            semantic_snippets = self.semantic_retriever.retrieve(
                query=current_message,
                platform=platform,
                chat_id=chat_id,
                limit=3,
            )
            for snippet in semantic_snippets:
                if any(m["content"] == snippet for m in context_messages):
                    continue
                context_messages.append(
                    {
                        "role": "assistant",
                        "content": snippet,
                        "timestamp": datetime.now().isoformat(),
                        "source": "llamaindex",
                    }
                )

        context_messages.sort(key=lambda x: x["timestamp"])
        atmosphere = self._estimate_chat_atmosphere(context_messages)
        summary = self._create_summary(context_messages, sources, hints, atmosphere)
        facts_total = sum(sources.values())
        rolling_share = (sources["rolling_recent_days"] / facts_total) if facts_total else 0.0
        if self.metrics:
            self.metrics.inc("rolling_memory_context_facts", value=sources["rolling_recent_days"], scope=f"{platform}:{chat_id}")
        self.logger.info(
            "Контекст собран: platform=%s chat_id=%s messages=%s atmosphere=%s rolling_share=%.3f",
            platform,
            chat_id,
            len(context_messages),
            atmosphere,
            rolling_share,
        )
        return {
            "messages": [{"role": m["role"], "content": m["content"]} for m in context_messages],
            "summary": summary,
            "total_tokens": used_tokens,
            "sources": sources,
            "persona_slice": persona_slice or {},
            "metadata": {
                "platform": platform,
                "chat_id": chat_id,
                "user_id": user_id,
                "context_size": len(context_messages),
                "strategy_hints": hints,
                "chat_atmosphere": atmosphere,
                "rolling_memory_share": round(rolling_share, 4),
                "persona_slice": persona_slice or {},
                "notebook_limits": notebook_limits,
            },
        }

    @staticmethod
    def _estimate_chat_atmosphere(messages: List[Dict[str, Any]]) -> str:
        if not messages:
            return "unknown"
        last_text = " ".join(m.get("content", "").lower() for m in messages[-5:])
        negative_markers = ("бесит", "туп", "ненав", "достал")
        positive_markers = ("спасибо", "класс", "люблю", "хаха")
        neg = sum(marker in last_text for marker in negative_markers)
        pos = sum(marker in last_text for marker in positive_markers)
        if neg > pos:
            return "toxic"
        if pos > neg:
            return "friendly"
        return "neutral"

    @staticmethod
    def _create_summary(messages: List[Dict[str, Any]], sources: Dict[str, int], hints: Dict[str, Any], atmosphere: str) -> str:
        if not messages:
            return "Новый диалог без предыстории."
        time_range = (datetime.fromisoformat(messages[0]["timestamp"]), datetime.fromisoformat(messages[-1]["timestamp"]))
        hints_line = ""
        if hints.get("avoid_topics"):
            hints_line = f"\n- Strategy hints: избегать тем {', '.join(hints['avoid_topics'])}"
        return (
            "Контекст диалога:\n"
            f"- Сообщений: {len(messages)} ({sources['notebook']} notebook, {sources['recent']} недавних, {sources['semantic']} релевантных, {sources['important']} важных, {sources['rolling_recent_days']} rolling-memory)\n"

            f"- Период: {time_range[0].strftime('%d.%m %H:%M')} - {time_range[1].strftime('%d.%m %H:%M')}\n"
            f"- Атмосфера чата: {atmosphere}"
            f"{hints_line}"
        )
