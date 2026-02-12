"""Главный класс NotyBot."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any, Dict, Mapping

from noty.core.adaptation_engine import AdaptationEngine
from noty.core.api_rotator import APIRotator
from noty.core.events import InteractionJSONLLogger, enrich_event_scope
from noty.core.message_handler import MessageHandler
from noty.core.response_processor import ResponseProcessor
from noty.memory.mem0_wrapper import Mem0Wrapper
from noty.memory.relationship_manager import RelationshipManager
from noty.memory.session_state import SessionStateStore
from noty.memory.sqlite_db import SQLiteDBManager
from noty.mood.mood_manager import MoodManager
from noty.thought.monologue import InternalMonologue
from noty.tools.tool_executor import SafeToolExecutor
from noty.transport.types import normalize_incoming_event
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
        self.adaptation_engine = adaptation_engine or AdaptationEngine()
        self.response_processor = response_processor or ResponseProcessor(tool_executor=self.tool_executor)
        self.logger = logging.getLogger(__name__)

    def handle_message(self, event: Mapping[str, Any]) -> Dict[str, Any]:
        payload = dict(event)
        payload.setdefault("username", f"user_{payload.get('user_id', 'unknown')}")
        payload.setdefault("chat_name", f"chat_{payload.get('chat_id', 'unknown')}")
        payload.setdefault("is_private", False)
        payload.setdefault("platform", "unknown")
        payload.setdefault("raw_event_id", f"raw:{datetime.now().timestamp()}")

        normalized = normalize_incoming_event(payload)
        event_data = enrich_event_scope(normalized.to_dict())

        chat_id = event_data["chat_id"]
        user_id = event_data["user_id"]
        text = event_data["text"]
        platform = event_data["platform"]
        scope = event_data["scope"]

        self.interaction_logger.log_incoming(event_data)

        relationship = payload.get("relationship")
        if not relationship and self.relationship_manager:
            relationship = self.relationship_manager.get_relationship(user_id)

        if self._should_refuse_private_chat(event_data, relationship):
            self.logger.info("ЛС отклонен по интересу: user_id=%s scope=%s", user_id, scope)
            self._log_interaction(event_data, responded=False, response_text="", tools_used=[])
            result = {
                "status": "ignored",
                "reason": "private_chat_uninteresting",
                "score": 0.0,
                "threshold": 1.0,
            }
            self.interaction_logger.log_outgoing(event_data, result)
            return result

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
            try:
                decision = self.message_handler.decide_reaction(text, scope=scope)
            except TypeError:
                decision = self.message_handler.decide_reaction(text)
            if not decision.should_respond:
                self._log_interaction(event_data, responded=False, response_text="", tools_used=[])
                result = {
                    "status": "ignored",
                    "reason": decision.reason,
                    "score": round(decision.score, 4),
                    "threshold": round(decision.threshold, 4),
                }
                self.interaction_logger.log_outgoing(event_data, result)
                return result

            mood_state = self.mood_manager.get_current_state()
            relationship_trend = self.relationship_manager.get_relationship_trend(user_id) if self.relationship_manager else {}
            pre_recommendation = self.adaptation_engine.recommend(
                interaction_outcome="success",
                user_feedback_signals=payload.get("feedback_signals", {}),
                relationship_trend=relationship_trend,
                filter_stats=self.message_handler.get_filter_stats(),
            )

            global_memory_summary = self._get_global_memory_summary(user_id=user_id, platform=platform, chat_id=chat_id)
            self.logger.info("Сформирована глобальная память: user_id=%s chars=%s", user_id, len(global_memory_summary))

            prompt = self.message_handler.prepare_prompt(
                platform=platform,
                chat_id=chat_id,
                user_id=user_id,
                message_text=text,
                mood=mood_state["mood"],
                energy=mood_state["energy"],
                user_relationship=relationship,
                runtime_modifiers={
                    "preferred_tone": pre_recommendation.preferred_tone,
                    "sarcasm_level": pre_recommendation.sarcasm_level,
                    "response_rate_bias": pre_recommendation.response_rate_bias,
                },
                strategy_hints=self._build_strategy_hints(payload),
            )
            if global_memory_summary:
                prompt = f"{prompt}\n\nGLOBAL_NOTY_MEMORY:\n{global_memory_summary}"

            thought_entry = self.monologue.generate_thoughts(
                {
                    "chat_id": chat_id,
                    "chat_name": event_data.get("chat_name", "unknown"),
                    "user_id": user_id,
                    "username": event_data.get("username", "unknown"),
                    "message": text,
                    "relationship_score": (relationship or {}).get("score", 0),
                    "mood": mood_state["mood"],
                    "energy": mood_state["energy"],
                },
                cheap_model=True,
            )

            with self.metrics.time_block("llm_call_seconds"):
                llm_response = self.api_rotator.call(messages=[{"role": "user", "content": prompt}])
            self.metrics.record_tokens(llm_response.get("usage"))

            strategy_name = thought_entry.get("strategy", "balanced")
            if strategy_name == "harsh_sarcasm":
                self.mood_manager.update_on_event("annoying_message")
            else:
                self.mood_manager.update_on_event("interesting_topic")

            processing_result = self.response_processor.process(
                llm_response,
                user_id=user_id,
                chat_id=chat_id,
                is_private=bool(event_data.get("is_private", False)),
            )
            self._apply_tool_post_processing(processing_result.tool_results)

            mood_after = self.mood_manager.get_current_state()
            response_text = processing_result.text
            self._log_interaction(
                event_data,
                responded=True,
                response_text=response_text,
                mood_before=mood_state["mood"],
                mood_after=mood_after["mood"],
                tools_used=processing_result.tools_used,
            )

            outcome = payload.get("interaction_outcome", processing_result.outcome)
            self._update_memory_after_response(
                event_data,
                response_text=response_text,
                outcome=outcome,
                tone_used=strategy_name,
                thought_quality=thought_entry.get("quality_score", 0.0),
            )

            recommendation = self._adapt_behavior_after_response(
                event=event_data,
                outcome=outcome,
                filter_stats=self.message_handler.get_filter_stats(),
            )

            result = {
                "status": "responded" if processing_result.status == "success" else processing_result.status,
                "text": response_text,
                "usage": llm_response.get("usage", {}),
                "finish_reason": llm_response.get("finish_reason"),
                "tool_results": processing_result.tool_results,
                "metrics": self.metrics.snapshot(),
                "filter_stats": self.message_handler.get_filter_stats(),
                "adaptation": recommendation,
            }
            self.interaction_logger.log_outgoing(event_data, result)
            return result

    @staticmethod
    def _build_strategy_hints(event: Mapping[str, Any]) -> Dict[str, Any]:
        hints: Dict[str, Any] = {}
        failed_topics = event.get("failed_topics", [])
        if failed_topics:
            hints["avoid_topics"] = failed_topics
        if event.get("previous_interaction_outcome") == "fail":
            hints.setdefault("avoid_topics", []).append("конфликт")
        return hints

    def _apply_tool_post_processing(self, tool_results: list[Dict[str, Any]]) -> None:
        if not tool_results:
            return
        for result in tool_results:
            status = result.get("status")
            if status == "success":
                self.mood_manager.update_on_event("interesting_topic", {"energy_cost": 1})
            elif status == "awaiting_confirmation":
                self.mood_manager.update_on_event("interesting_topic", {"energy_cost": 0})
            elif status in {"forbidden", "validation_error", "runtime_error"}:
                self.mood_manager.update_on_event("insulted", {"energy_cost": 1})

    def _log_interaction(
        self,
        event: Mapping[str, Any],
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
        event: Mapping[str, Any],
        response_text: str,
        outcome: str,
        tone_used: str = "balanced",
        thought_quality: float = 0.0,
    ) -> None:
        if self.relationship_manager:
            username = event.get("username") or f"user_{event['user_id']}"
            interaction_outcome = "positive" if outcome == "success" else "negative"
            self.relationship_manager.update_relationship(
                user_id=event["user_id"],
                username=username,
                interaction_outcome=interaction_outcome,
                notes=f"Взаимодействие в чате {event['chat_id']} с outcome={outcome}; thought_quality={thought_quality}",
                tone_used=tone_used,
            )

        if self.mem0:
            self.mem0.remember_interaction(
                user_id=f"user_{event['user_id']}",
                message=event["text"],
                response=response_text,
                outcome=outcome,
                metadata={"platform": event.get("platform", "unknown"), "chat_id": event["chat_id"]},
            )

    def _adapt_behavior_after_response(self, event: Mapping[str, Any], outcome: str, filter_stats: Dict[str, Any]) -> Dict[str, Any]:
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

    @staticmethod
    def _relationship_score(relationship: Mapping[str, Any] | None) -> int:
        if not relationship:
            return 0
        return int(relationship.get("relationship_score", relationship.get("score", 0)) or 0)

    def _should_refuse_private_chat(self, event: Mapping[str, Any], relationship: Mapping[str, Any] | None) -> bool:
        if not bool(event.get("is_private", False)):
            return False
        score = self._relationship_score(relationship)
        return score <= -3

    def _get_global_memory_summary(self, user_id: int, platform: str, chat_id: int) -> str:
        if not self.mem0:
            return ""
        recalls = self.mem0.recall(
            query="долгосрочные факты о пользователе и моем отношении",
            user_id=f"user_{user_id}",
            limit=5,
        )
        if not recalls:
            return ""

        parts: list[str] = []
        for item in recalls:
            text = item.get("text", "").strip()
            metadata = item.get("metadata", {})
            item_platform = metadata.get("platform", "global")
            item_chat = metadata.get("chat_id", "*")
            scope_mark = "global" if item_platform == platform and item_chat == chat_id else f"{item_platform}:{item_chat}"
            if text:
                parts.append(f"- [{scope_mark}] {text[:180]}")
        return "\n".join(parts)
