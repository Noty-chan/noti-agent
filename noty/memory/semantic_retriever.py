"""Семантический ретривер поверх LlamaIndex для расширения контекста."""

from __future__ import annotations

import logging
from typing import Any, Dict, List


class LlamaSemanticRetriever:
    """Опциональный ретривер: при недоступности LlamaIndex возвращает пустой результат."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._index = None

    def ingest(self, records: List[Dict[str, Any]]) -> None:
        if not records:
            return
        try:
            from llama_index.core import Document, VectorStoreIndex
        except Exception as exc:  # noqa: BLE001
            self.logger.info("LlamaIndex не активирован для ingest: %s", exc)
            return

        documents = [
            Document(
                text=item.get("text", ""),
                metadata={
                    "platform": item.get("platform", "unknown"),
                    "chat_id": item.get("chat_id"),
                    "user_id": item.get("user_id"),
                },
            )
            for item in records
            if item.get("text")
        ]
        if not documents:
            return
        self._index = VectorStoreIndex.from_documents(documents)
        self.logger.info("LlamaIndex ingest завершен: %s документов", len(documents))

    def retrieve(self, query: str, platform: str, chat_id: int, limit: int = 3) -> List[str]:
        if not query:
            return []
        if self._index is None:
            return []

        retriever = self._index.as_retriever(similarity_top_k=limit * 2)
        nodes = retriever.retrieve(query)
        matched: List[str] = []
        for node in nodes:
            meta = getattr(node, "metadata", {}) or {}
            if meta.get("platform") != platform or meta.get("chat_id") != chat_id:
                continue
            content = getattr(node, "text", "")
            if content:
                matched.append(content)
            if len(matched) >= limit:
                break
        return matched
