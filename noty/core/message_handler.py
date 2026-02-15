"""Оркестрация обработки входящих сообщений."""

from __future__ import annotations

from typing import Any, Dict

from noty.core.context_manager import DynamicContextBuilder
from noty.filters.embedding_filter import EmbeddingFilter
from noty.filters.heuristic_filter import HeuristicFilter
from noty.filters.reaction_decider import ReactionDecision, ReactionDecider
from noty.prompts.prompt_builder import ModularPromptBuilder
from noty.transport.types import IncomingEvent, normalize_incoming_event
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
        return self.decide_reaction(message_text).should_respond

    def should_react_to_event(self, event: IncomingEvent | Dict[str, Any]) -> bool:
        normalized = normalize_incoming_event(event)
        return self.should_react(normalized.text)

    def decide_reaction(self, message_text: str, scope: str | None = None) -> ReactionDecision:
        with self.metrics.time_block("filter_pipeline_seconds", stage="filter_pipeline", platform=scope.split(":", 1)[0] if scope else None):
            heuristic_passed = self.heuristic_filter.should_check_embeddings(message_text)
            self.metrics.inc("messages_total", scope=scope)

            if not heuristic_passed:
                self.metrics.inc("heuristic_dropped", scope=scope)
                return ReactionDecision(False, 0.0, 1.0, 0.0, "heuristic_drop")

            is_interesting, score, _topic = self.embedding_filter.is_interesting(message_text, return_score=True)
            if not is_interesting:
                self.metrics.inc("embedding_dropped", scope=scope)

            heuristic_boost = 0.1 if heuristic_passed else 0.0
            decision = self.reaction_decider.decide(score, heuristic_boost=heuristic_boost)
            self.metrics.inc("responded_by_decider" if decision.should_respond else "randomized_drop", scope=scope)
            return decision

    def prepare_prompt(
        self,
        platform: str,
        chat_id: int,
        user_id: int,
        message_text: str,
        mood: str = "neutral",
        energy: int = 100,
        user_relationship: Dict[str, Any] | None = None,
        runtime_modifiers: Dict[str, Any] | None = None,
        strategy_hints: Dict[str, Any] | None = None,
        persona_profile: Dict[str, Any] | None = None,
        thought_context: Dict[str, Any] | None = None,
        environment_context: Dict[str, Any] | None = None,
    ) -> str:
        with self.metrics.time_block("context_build_seconds", stage="context_build", platform=platform):
            context = self.context_builder.build_context(
                chat_id=chat_id,
                current_message=message_text,
                user_id=user_id,
                strategy_hints=strategy_hints,
                platform=platform,
                persona_slice=persona_profile or {},
            )

        return self.prompt_builder.build_full_prompt(
            context=context,
            mood=mood,
            energy=energy,
            user_relationship=user_relationship,
            runtime_modifiers=runtime_modifiers,
            persona_profile=persona_profile,
            thought_context=thought_context,
            environment_context=environment_context,
        )

    def get_filter_stats(self) -> Dict[str, Any]:
        return {"decider": self.reaction_decider.stats(), "metrics": self.metrics.snapshot()}
