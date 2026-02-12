"""Гибридный сборщик контекста: recent + semantic + important."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

import numpy as np

from noty.filters.embedding_filter import EmbeddingFilter


class DynamicContextBuilder:
    def __init__(self, db_manager: Any, embedding_filter: EmbeddingFilter, max_tokens: int = 3000):
        self.db = db_manager
        self.embedder = embedding_filter
        self.max_tokens = max_tokens

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return len(text) // 4


    def build_context(self, platform: str, chat_id: int, current_message: str, user_id: int) -> Dict[str, Any]:

    def build_context(
        self,
        chat_id: int,
        current_message: str,
        user_id: int,
        strategy_hints: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:

        context_messages: List[Dict[str, Any]] = []
        used_tokens = 0
        sources = {"recent": 0, "semantic": 0, "important": 0}
        hints = strategy_hints or {}

        recent_messages = self.db.get_recent_messages(platform, chat_id, limit=5)
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

        past_messages = self.db.get_messages_range(platform, chat_id, days_ago=7, exclude_recent=5)
        if past_messages:
            msg_texts = [m["text"] for m in past_messages]
            current_emb = self.embedder.encoder.encode(current_message)
            similarities = []
            for i, msg_text in enumerate(msg_texts):
                msg_emb = self.embedder.encoder.encode(msg_text)
                sim = np.dot(current_emb, msg_emb) / (
                    np.linalg.norm(current_emb) * np.linalg.norm(msg_emb)
                )
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

        important_messages = self.db.get_important_messages(platform, chat_id, days_ago=7)
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


        conflict_topics = [t.lower() for t in hints.get("avoid_topics", [])]
        if conflict_topics:
            context_messages = [
                msg
                for msg in context_messages
                if not any(topic in msg["content"].lower() for topic in conflict_topics)
            ]

        context_messages.sort(key=lambda x: x["timestamp"])
        summary = self._create_summary(context_messages, sources, hints)
        return {
            "messages": [{"role": m["role"], "content": m["content"]} for m in context_messages],
            "summary": summary,
            "total_tokens": used_tokens,
            "sources": sources,
            "metadata": {

                "platform": platform,
                "chat_id": chat_id,
                "user_id": user_id,
                "context_size": len(context_messages),

                "chat_id": chat_id,
                "user_id": user_id,
                "context_size": len(context_messages),
                "strategy_hints": hints,

            },
        }

    @staticmethod
    def _create_summary(messages: List[Dict[str, Any]], sources: Dict[str, int], hints: Dict[str, Any]) -> str:
        if not messages:
            return "Новый диалог без предыстории."
        time_range = (
            datetime.fromisoformat(messages[0]["timestamp"]),
            datetime.fromisoformat(messages[-1]["timestamp"]),
        )
        hints_line = ""
        if hints.get("avoid_topics"):
            hints_line = f"\n- Strategy hints: избегать тем {', '.join(hints['avoid_topics'])}"
        return (
            "Контекст диалога:\n"
            f"- Сообщений: {len(messages)} ({sources['recent']} недавних, {sources['semantic']} релевантных, {sources['important']} важных)\n"
            f"- Период: {time_range[0].strftime('%d.%m %H:%M')} - {time_range[1].strftime('%d.%m %H:%M')}"
            f"{hints_line}"
        )
