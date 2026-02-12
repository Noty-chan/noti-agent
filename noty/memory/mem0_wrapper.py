"""Обёртка над Mem0 для семантической памяти."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from mem0 import Memory


class Mem0Wrapper:
    def __init__(self, config: Optional[Dict] = None, memory_client: Optional[Memory] = None):
        default_config = {
            "vector_store": {"provider": "qdrant", "config": {"path": "./noty/data/qdrant_db", "collection_name": "noty_memories"}},
            "embedder": {"provider": "sentence_transformers", "config": {"model": "intfloat/multilingual-e5-base"}},
        }
        self.memory = memory_client or Memory.from_config(config or default_config)

    def remember(
        self,
        text: str,
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        platform: Optional[str] = None,
        chat_id: Optional[int] = None,
    ):
        metadata = metadata or {}
        metadata["timestamp"] = datetime.now().isoformat()
        if platform is not None:
            metadata["platform"] = platform
        if chat_id is not None:
            metadata["chat_id"] = chat_id
        self.memory.add(text, user_id=user_id, metadata=metadata)

    def recall(
        self,
        query: str,
        user_id: Optional[str] = None,
        limit: int = 5,
        platform: Optional[str] = None,
        chat_id: Optional[int] = None,
    ) -> List[Dict]:
        results = self.memory.search(query, user_id=user_id, limit=limit)
        if platform is None and chat_id is None:
            return results

        filtered: List[Dict] = []
        for item in results:
            metadata = item.get("metadata", {})
            if platform is not None and metadata.get("platform") != platform:
                continue
            if chat_id is not None and metadata.get("chat_id") != chat_id:
                continue
            filtered.append(item)
        return filtered

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
        self.remember(
            memory_text,
            user_id=user_id,
            metadata=payload,
            platform=payload.get("platform"),
            chat_id=payload.get("chat_id"),
        )

    def get_user_summary(self, user_id: str) -> str:
        memories = self.recall("отношения с этим пользователем", user_id=user_id, limit=10)
        if not memories:
            return "Новый пользователь, ничего не помню."
        return "\n".join(f"- {m['text'][:100]}..." for m in memories[:5])
