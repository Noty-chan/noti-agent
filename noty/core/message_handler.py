"""Оркестрация обработки входящих сообщений."""

from __future__ import annotations

from typing import Any, Dict

from noty.core.context_manager import DynamicContextBuilder
from noty.filters.embedding_filter import EmbeddingFilter
from noty.filters.heuristic_filter import HeuristicFilter
from noty.prompts.prompt_builder import ModularPromptBuilder


class MessageHandler:
    def __init__(
        self,
        context_builder: DynamicContextBuilder,
        prompt_builder: ModularPromptBuilder,
        heuristic_filter: HeuristicFilter,
        embedding_filter: EmbeddingFilter,
    ):
        self.context_builder = context_builder
        self.prompt_builder = prompt_builder
        self.heuristic_filter = heuristic_filter
        self.embedding_filter = embedding_filter

    def should_react(self, message_text: str) -> bool:
        if not self.heuristic_filter.should_check_embeddings(message_text):
            return False
        return self.embedding_filter.is_interesting(message_text)

    def prepare_prompt(
        self,
        chat_id: int,
        user_id: int,
        message_text: str,
        mood: str = "neutral",
        energy: int = 100,
        user_relationship: Dict[str, Any] | None = None,
    ) -> str:
        context = self.context_builder.build_context(chat_id, message_text, user_id)
        return self.prompt_builder.build_full_prompt(
            context=context,
            mood=mood,
            energy=energy,
            user_relationship=user_relationship,
        )
