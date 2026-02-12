"""Главный класс NotyBot."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4
from typing import Any, Dict


from noty.core.events import IncomingEvent, InteractionJSONLLogger

from noty.core.adaptation_engine import AdaptationEngine

from noty.core.api_rotator import APIRotator
from noty.core.events import enrich_event_scope
from noty.core.message_handler import MessageHandler
from noty.memory.mem0_wrapper import Mem0Wrapper
from noty.memory.relationship_manager import RelationshipManager
from noty.memory.session_state import SessionStateStore
from noty.memory.sqlite_db import SQLiteDBManager
from noty.mood.mood_manager import MoodManager
from noty.thought.monologue import InternalMonologue
from noty.tools.tool_executor import SafeToolExecutor
from noty.core.response_processor import ResponseProcessor
from noty.utils.metrics import MetricsCollector


class NotyBot:
    def __init__(
        self,
        api_rotator: APIRotator,
        message_handler: MessageHandler,
        mood_manager: MoodManager,
        tool_executor: SafeToolExecutor,
        monologue: InternalMonologue,
        db_manager: SQLiteDBManager | None = None,
        mem0: Mem0Wrapper | None = None,
        relationship_manager: RelationshipManager | None = None,
        session_store: SessionStateStore | None = None,
        metrics: MetricsCollector | None = None,

        interaction_logger: InteractionJSONLLogger | None = None,

        adaptation_engine: AdaptationEngine | None = None,

        response_processor: ResponseProcessor | None = None,

    ):
        self.api_rotator = api_rotator
        self.message_handler = message_handler
        self.mood_manager = mood_manager
        self.tool_executor = tool_executor
        self.monologue = monologue
        self.db_manager = db_manager
        self.mem0 = mem0
        self.relationship_manager = relationship_manager
        self.session_store = session_store or SessionStateStore()
        self.metrics = metrics or MetricsCollector()

        self.interaction_logger = interaction_logger or InteractionJSONLLogger()

    def handle_message(self, event: IncomingEvent) -> Dict[str, Any]:
        chat_id = event.chat_id
        user_id = event.user_id
        text = event.text

        self.adaptation_engine = adaptation_engine or AdaptationEngine()
        self.response_processor = response_processor or ResponseProcessor()

    def handle_message(self, event: Dict[str, Any]) -> Dict[str, Any]:
        event = enrich_event_scope(event)
        scope = event["scope"]
        chat_id = event["chat_id"]
        user_id = event["user_id"]
        text = event["text"]

        platform = event["platform"]

        interaction_id = event.get("interaction_id", f"{chat_id}:{uuid4().hex[:12]}")


        self.interaction_logger.log_incoming(event)

        relationship = event.relationship
        if not relationship and self.relationship_manager:
            relationship = self.relationship_manager.get_relationship(user_id)

        self.session_store.set(
            "chat",
            scope,
            {
                "last_user_id": user_id,
                "last_message": text,
                "updated_at": datetime.now().isoformat(),
                "awake": True,
            },
        )

        with self.metrics.time_block("message_total_seconds"):
            decision = self.message_handler.decide_reaction(text, scope=scope)
            if not decision.should_respond:
                self._log_interaction(event, responded=False, response_text="", tools_used=[])
                result = {
                    "status": "ignored",
                    "reason": decision.reason,
                    "score": round(decision.score, 4),
                    "threshold": round(decision.threshold, 4),
                }
                self.interaction_logger.log_outgoing(event, result)
                return result

            mood_state = self.mood_manager.get_current_state()
            relationship_trend = self.relationship_manager.get_relationship_trend(user_id) if self.relationship_manager else {}
            pre_recommendation = self.adaptation_engine.recommend(
                interaction_outcome="success",
                user_feedback_signals=event.get("feedback_signals", {}),
                relationship_trend=relationship_trend,
                filter_stats=self.message_handler.get_filter_stats(),
            )
            runtime_modifiers = {
                "preferred_tone": pre_recommendation.preferred_tone,
                "sarcasm_level": pre_recommendation.sarcasm_level,
                "response_rate_bias": pre_recommendation.response_rate_bias,
            }
            strategy_hints = self._build_strategy_hints(event)
            prompt = self.message_handler.prepare_prompt(
                chat_id=chat_id,
                platform=platform,
                user_id=user_id,
                message_text=text,
                mood=mood_state["mood"],
                energy=mood_state["energy"],
                user_relationship=relationship,
                runtime_modifiers=runtime_modifiers,
                strategy_hints=strategy_hints,
            )

            thought_entry = self.monologue.generate_thoughts(
                {
                    "chat_id": chat_id,
                    "chat_name": event.chat_name or "Unknown",
                    "user_id": user_id,
                    "username": event.username or "unknown",
                    "message": text,
                    "interaction_id": interaction_id,
                    "relationship_score": event.get("relationship", {}).get("score", 0),

                    "relationship_score": (event.relationship or {}).get("score", 0),

                    "mood": mood_state["mood"],
                    "energy": mood_state["energy"],
                },
                cheap_model=True,
            )

            with self.metrics.time_block("llm_call_seconds"):
                llm_response = self.api_rotator.call(messages=[{"role": "user", "content": prompt}])

            self.metrics.record_tokens(llm_response.get("usage"), scope=scope)
            strategy = thought_entry.get("strategy", "balanced")
            if strategy == "harsh_sarcasm":

            self.metrics.record_tokens(llm_response.get("usage"))
            strategy_name = thought_entry.get("strategy", "balanced")
            applied_strategy = thought_entry.get("applied_strategy", {"name": strategy_name})
            processed_response = self.response_processor.process(
                llm_response=llm_response,
                strategy=applied_strategy,
                tools_registry=self.tool_executor.tools_registry,
            )
            if strategy_name == "harsh_sarcasm":

                self.mood_manager.update_on_event("annoying_message")
            else:
                self.mood_manager.update_on_event("interesting_topic")
            mood_after = self.mood_manager.get_current_state()
            response_text = processed_response["text"]

            tool_calls = processed_response.get("selected_tools", [])
            tools_used = [t.get("name") for t in tool_calls if t.get("name")]
            for tool_call in tool_calls:
                tool_name = tool_call.get("name")
                if not tool_name:
                    continue
                tool_info = self.tool_executor.tools_registry.get(tool_name, {})
                if processed_response.get("confirmation_escalation"):
                    tool_info["requires_confirmation"] = True
                self.tool_executor.execute(
                    tool_call,
                    user_id=user_id,
                    chat_id=chat_id,
                    is_private=event.get("is_private", False),
                )

            self._log_interaction(
                event,
                responded=True,
                response_text=response_text,
                mood_before=mood_state["mood"],
                mood_after=mood_after["mood"],
                tools_used=tools_used,
            )
            outcome = event.get("interaction_outcome", "success")
            self._update_memory_after_response(
                event,
                response_text=response_text,
                outcome=outcome,
                tone_used=strategy_name,
                thought_quality=thought_entry.get("quality_score", 0.0),
            )


            result = {

            recommendation = self._adapt_behavior_after_response(
                event=event,
                outcome=outcome,
                filter_stats=self.message_handler.get_filter_stats(),
            )

            return {

                "status": "responded",
                "text": response_text,
                "usage": llm_response.get("usage", {}),
                "finish_reason": llm_response.get("finish_reason"),
                "strategy": processed_response.get("strategy_used", {}),
                "interaction_id": interaction_id,
                "metrics": self.metrics.snapshot(),
                "filter_stats": self.message_handler.get_filter_stats(),
                "adaptation": recommendation,
            }
            self.interaction_logger.log_outgoing(event, result)
            return result


    @staticmethod
    def _build_strategy_hints(event: Dict[str, Any]) -> Dict[str, Any]:
        hints: Dict[str, Any] = {}
        failed_topics = event.get("failed_topics", [])
        if failed_topics:
            hints["avoid_topics"] = failed_topics
        if event.get("previous_interaction_outcome") == "fail":
            hints.setdefault("avoid_topics", []).append("конфликт")
        return hints

    def _log_interaction(
        self,
        event: IncomingEvent,
        responded: bool,
        response_text: str,
        mood_before: str = "neutral",
        mood_after: str = "neutral",
        tools_used: list[str] | None = None,
    ) -> None:
        if not self.db_manager:
            return
        conn = self.db_manager._connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO interactions (timestamp, platform, chat_id, user_id, message_text, noty_responded, response_text, mood_before, mood_after, tools_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(),

                event.get("platform", "unknown"),
                event["chat_id"],
                event["user_id"],
                event["text"],

                event.chat_id,
                event.user_id,
                event.text,

                int(responded),
                response_text,
                mood_before,
                mood_after,
                ",".join(tools_used or []),
            ),
        )
        conn.commit()
        conn.close()

    def _update_memory_after_response(
        self,
        event: IncomingEvent,
        response_text: str,
        outcome: str,
        tone_used: str = "balanced",
        thought_quality: float = 0.0,
    ) -> None:
        if self.relationship_manager:
            username = event.username or f"user_{event.user_id}"
            interaction_outcome = "positive" if outcome == "success" else "negative"
            self.relationship_manager.update_relationship(
                user_id=event.user_id,
                username=username,
                interaction_outcome=interaction_outcome,
                notes=f"Взаимодействие в чате {event.chat_id} с outcome={outcome}; thought_quality={thought_quality}",
                tone_used=tone_used,
            )

        if self.mem0:
            self.mem0.remember_interaction(
                user_id=f"user_{event.user_id}",
                message=event.text,
                response=response_text,
                outcome=outcome,

                metadata={"platform": event.get("platform", "unknown"), "chat_id": event["chat_id"]},
=======
                metadata={"chat_id": event.chat_id},

            )

    def _adapt_behavior_after_response(
        self,
        event: Dict[str, Any],
        outcome: str,
        filter_stats: Dict[str, Any],
    ) -> Dict[str, Any]:
        relationship_trend = self.relationship_manager.get_relationship_trend(event["user_id"]) if self.relationship_manager else {}
        recommendation = self.adaptation_engine.recommend(
            interaction_outcome=outcome,
            user_feedback_signals=event.get("feedback_signals", {}),
            relationship_trend=relationship_trend,
            filter_stats=filter_stats,
        )
        approved = outcome == "success" and not recommendation.rollback_required
        applied_version = self.message_handler.prompt_builder.current_personality_version
        rollback_version = None
        if recommendation.rollback_required:
            try:
                rollback_version = self.message_handler.prompt_builder.rollback_personality_version()
                applied_version = rollback_version
                approved = False
            except ValueError:
                rollback_version = None

        self._log_prompt_adjustment(
            reason=recommendation.reason,
            signal_source=recommendation.signal_source,
            approved=approved,
            personality_layer=(
                f"tone={recommendation.preferred_tone}; "
                f"sarcasm={recommendation.sarcasm_level:.2f}; "
                f"response_rate_bias={recommendation.response_rate_bias:+.2f}; "
                f"version=v{applied_version}; rollback={rollback_version}"
            ),
            mood_layer=self.mood_manager.get_current_state()["mood"],
        )

        return {
            "preferred_tone": recommendation.preferred_tone,
            "sarcasm_level": recommendation.sarcasm_level,
            "response_rate_bias": recommendation.response_rate_bias,
            "rollback_applied": rollback_version is not None,
            "rollback_version": rollback_version,
            "approved": approved,
        }

    def _log_prompt_adjustment(
        self,
        reason: str,
        signal_source: str,
        approved: bool,
        personality_layer: str,
        mood_layer: str,
    ) -> None:
        if not self.db_manager:
            return
        conn = self.db_manager._connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO prompt_versions (created_at, personality_layer, mood_layer, reason_for_change, signal_source, approved)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(),
                personality_layer,
                mood_layer,
                reason,
                signal_source,
                int(approved),
            ),
        )
        conn.commit()
        conn.close()
