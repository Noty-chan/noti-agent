"""Оркестрация обработки входящих сообщений."""

from __future__ import annotations

from typing import Any, Dict

from noty.core.context_manager import DynamicContextBuilder
from noty.filters.embedding_filter import EmbeddingFilter
from noty.filters.heuristic_filter import HeuristicFilter
from noty.filters.reaction_decider import ReactionDecision, ReactionDecider
from noty.prompts.prompt_builder import ModularPromptBuilder
from noty.utils.metrics import MetricsCollector


class MessageHandler:
    def __init__(
        self,
        context_builder: DynamicContextBuilder,
        prompt_builder: ModularPromptBuilder,
        heuristic_filter: HeuristicFilter,
        embedding_filter: EmbeddingFilter,
        reaction_decider: ReactionDecider | None = None,
        metrics: MetricsCollector | None = None,
    ):
        self.context_builder = context_builder
        self.prompt_builder = prompt_builder
        self.heuristic_filter = heuristic_filter
        self.embedding_filter = embedding_filter
        self.reaction_decider = reaction_decider or ReactionDecider()
        self.metrics = metrics or MetricsCollector()

    def should_react(self, message_text: str) -> bool:
        decision = self.decide_reaction(message_text)
        return decision.should_respond

    def decide_reaction(self, message_text: str) -> ReactionDecision:
        with self.metrics.time_block("filter_pipeline_seconds"):
            heuristic_passed = self.heuristic_filter.should_check_embeddings(message_text)
            self.metrics.inc("messages_total")

            if not heuristic_passed:
                self.metrics.inc("heuristic_dropped")
                return ReactionDecision(False, 0.0, 1.0, 0.0, "heuristic_drop")

            is_interesting, score, _topic = self.embedding_filter.is_interesting(message_text, return_score=True)
            if not is_interesting:
                self.metrics.inc("embedding_dropped")

            heuristic_boost = 0.1 if heuristic_passed else 0.0
            decision = self.reaction_decider.decide(score, heuristic_boost=heuristic_boost)
            self.metrics.inc("responded_by_decider" if decision.should_respond else "randomized_drop")
            return decision

    def prepare_prompt(
        self,
        chat_id: int,
        user_id: int,
        message_text: str,
        mood: str = "neutral",
        energy: int = 100,
        user_relationship: Dict[str, Any] | None = None,
    ) -> str:
        with self.metrics.time_block("context_build_seconds"):
            context = self.context_builder.build_context(chat_id, message_text, user_id)
        return self.prompt_builder.build_full_prompt(
            context=context,
            mood=mood,
            energy=energy,
            user_relationship=user_relationship,
        )

    def get_filter_stats(self) -> Dict[str, Any]:
        return {
            "decider": self.reaction_decider.stats(),
            "metrics": self.metrics.snapshot(),
        }
