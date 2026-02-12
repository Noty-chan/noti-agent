"""Главный класс NotyBot."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from noty.core.adaptation_engine import AdaptationEngine
from noty.core.api_rotator import APIRotator
from noty.core.message_handler import MessageHandler
from noty.memory.mem0_wrapper import Mem0Wrapper
from noty.memory.relationship_manager import RelationshipManager
from noty.memory.session_state import SessionStateStore
from noty.memory.sqlite_db import SQLiteDBManager
from noty.mood.mood_manager import MoodManager
from noty.thought.monologue import InternalMonologue
from noty.tools.tool_executor import SafeToolExecutor
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
        adaptation_engine: AdaptationEngine | None = None,
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
        self.adaptation_engine = adaptation_engine or AdaptationEngine()

    def handle_message(self, event: Dict[str, Any]) -> Dict[str, Any]:
        chat_id = event["chat_id"]
        user_id = event["user_id"]
        text = event["text"]

        relationship = event.get("relationship")
        if not relationship and self.relationship_manager:
            relationship = self.relationship_manager.get_relationship(user_id)

        self.session_store.set(
            f"chat:{chat_id}",
            {
                "last_user_id": user_id,
                "last_message": text,
                "updated_at": datetime.now().isoformat(),
                "awake": True,
            },
        )

        with self.metrics.time_block("message_total_seconds"):
            decision = self.message_handler.decide_reaction(text)
            if not decision.should_respond:
                self._log_interaction(event, responded=False, response_text="", tools_used=[])
                return {
                    "status": "ignored",
                    "reason": decision.reason,
                    "score": round(decision.score, 4),
                    "threshold": round(decision.threshold, 4),
                }

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
            prompt = self.message_handler.prepare_prompt(
                chat_id=chat_id,
                user_id=user_id,
                message_text=text,
                mood=mood_state["mood"],
                energy=mood_state["energy"],
                user_relationship=relationship,
                runtime_modifiers=runtime_modifiers,
            )

            thought_entry = self.monologue.generate_thoughts(
                {
                    "chat_id": chat_id,
                    "chat_name": event.get("chat_name", "Unknown"),
                    "user_id": user_id,
                    "username": event.get("username", "unknown"),
                    "message": text,
                    "relationship_score": event.get("relationship", {}).get("score", 0),
                    "mood": mood_state["mood"],
                    "energy": mood_state["energy"],
                },
                cheap_model=True,
            )

            with self.metrics.time_block("llm_call_seconds"):
                llm_response = self.api_rotator.call(messages=[{"role": "user", "content": prompt}])

            self.metrics.record_tokens(llm_response.get("usage"))
            strategy = thought_entry.get("strategy", "balanced")
            if strategy == "harsh_sarcasm":
                self.mood_manager.update_on_event("annoying_message")
            else:
                self.mood_manager.update_on_event("interesting_topic")
            mood_after = self.mood_manager.get_current_state()
            response_text = llm_response.get("content", "")

            self._log_interaction(
                event,
                responded=True,
                response_text=response_text,
                mood_before=mood_state["mood"],
                mood_after=mood_after["mood"],
                tools_used=[],
            )
            outcome = event.get("interaction_outcome", "success")
            self._update_memory_after_response(
                event,
                response_text=response_text,
                outcome=outcome,
                tone_used=strategy,
                thought_quality=thought_entry.get("quality_score", 0.0),
            )

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
                "metrics": self.metrics.snapshot(),
                "filter_stats": self.message_handler.get_filter_stats(),
                "adaptation": recommendation,
            }

    def _log_interaction(
        self,
        event: Dict[str, Any],
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
            INSERT INTO interactions (timestamp, chat_id, user_id, message_text, noty_responded, response_text, mood_before, mood_after, tools_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(),
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
        event: Dict[str, Any],
        response_text: str,
        outcome: str,
        tone_used: str = "balanced",
        thought_quality: float = 0.0,
    ) -> None:
        if self.relationship_manager:
            username = event.get("username", f"user_{event['user_id']}")
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
                metadata={"chat_id": event["chat_id"]},
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
