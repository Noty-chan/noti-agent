"""Обёртка над Mem0 для семантической памяти."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from mem0 import Memory


class Mem0Wrapper:
    def __init__(self, config: Optional[Dict] = None):
        default_config = {
            "vector_store": {"provider": "qdrant", "config": {"path": "./noty/data/qdrant_db", "collection_name": "noty_memories"}},
            "embedder": {"provider": "sentence_transformers", "config": {"model": "intfloat/multilingual-e5-base"}},
        }
        self.memory = Memory.from_config(config or default_config)

    def remember(self, text: str, user_id: Optional[str] = None, metadata: Optional[Dict] = None):
        metadata = metadata or {}
        metadata["timestamp"] = datetime.now().isoformat()
        self.memory.add(text, user_id=user_id, metadata=metadata)

    def recall(self, query: str, user_id: Optional[str] = None, limit: int = 5) -> List[Dict]:
        return self.memory.search(query, user_id=user_id, limit=limit)

    def remember_interaction(
        self,
        user_id: str,
        message: str,
        response: str,
        outcome: str,
        metadata: Optional[Dict] = None,
    ):
        memory_text = f"Пользователь написал: '{message}'\nЯ ответила: '{response}'\nРезультат: {outcome}"
        payload = metadata or {}
        payload.update({"type": "interaction", "outcome": outcome, "timestamp": datetime.now().isoformat()})
        self.remember(memory_text, user_id=user_id, metadata=payload)

    def get_user_summary(self, user_id: str) -> str:
        memories = self.recall("отношения с этим пользователем", user_id=user_id, limit=10)
        if not memories:
            return "Новый пользователь, ничего не помню."
        return "\n".join(f"- {m['text'][:100]}..." for m in memories[:5])
