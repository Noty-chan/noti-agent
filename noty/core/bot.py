"""Главный класс NotyBot."""

from __future__ import annotations

from typing import Any, Dict

from noty.core.api_rotator import APIRotator
from noty.core.message_handler import MessageHandler
from noty.mood.mood_manager import MoodManager
from noty.thought.monologue import InternalMonologue
from noty.tools.tool_executor import SafeToolExecutor


class NotyBot:
    def __init__(
        self,
        api_rotator: APIRotator,
        message_handler: MessageHandler,
        mood_manager: MoodManager,
        tool_executor: SafeToolExecutor,
        monologue: InternalMonologue,
    ):
        self.api_rotator = api_rotator
        self.message_handler = message_handler
        self.mood_manager = mood_manager
        self.tool_executor = tool_executor
        self.monologue = monologue

    def handle_message(self, event: Dict[str, Any]) -> Dict[str, Any]:
        chat_id = event["chat_id"]
        user_id = event["user_id"]
        text = event["text"]

        if not self.message_handler.should_react(text):
            return {"status": "ignored", "reason": "not_interesting"}

        mood_state = self.mood_manager.get_current_state()
        prompt = self.message_handler.prepare_prompt(
            chat_id=chat_id,
            user_id=user_id,
            message_text=text,
            mood=mood_state["mood"],
            energy=mood_state["energy"],
            user_relationship=event.get("relationship"),
        )

        self.monologue.generate_thoughts(
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

        llm_response = self.api_rotator.call(messages=[{"role": "user", "content": prompt}])
        self.mood_manager.update_on_event("interesting_topic")

        return {
            "status": "responded",
            "text": llm_response["content"],
            "usage": llm_response.get("usage", {}),
            "finish_reason": llm_response.get("finish_reason"),
        }
