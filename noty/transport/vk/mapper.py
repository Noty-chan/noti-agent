"""Маппинг VK update в IncomingEvent."""

from __future__ import annotations

from typing import Any, Dict

from noty.core.events import IncomingEvent


def map_vk_update_to_incoming_event(update: Dict[str, Any]) -> IncomingEvent | None:
    if update.get("type") != "message_new":
        return None

    object_data = update.get("object", {})
    message = object_data.get("message", {})
    text = (message.get("text") or "").strip()
    if not text:
        return None

    chat_id = message.get("peer_id")
    user_id = message.get("from_id")
    if chat_id is None or user_id is None:
        return None

    return IncomingEvent(
        platform="vk",
        chat_id=int(chat_id),
        user_id=int(user_id),
        text=text,
        update_id=update.get("event_id") or message.get("conversation_message_id") or message.get("id"),
        chat_name=None,
        username=None,
        metadata={
            "raw_update_type": update.get("type"),
            "raw_object": object_data,
        },
    )
