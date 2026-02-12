"""Mapper VK callback/polling event -> IncomingEvent."""

from __future__ import annotations

from typing import Any

from noty.transport.types import IncomingEvent


VK_MESSAGE_NEW = "message_new"


def map_vk_event(event: dict[str, Any]) -> IncomingEvent:
    event_type = event.get("type")
    if event_type != VK_MESSAGE_NEW:
        raise ValueError(f"Неподдерживаемый VK event type: {event_type}")

    obj = event.get("object", {})
    message = obj.get("message", obj)

    peer_id = message.get("peer_id") or message.get("chat_id")
    from_id = message.get("from_id") or message.get("user_id")
    text = message.get("text", "")

    if peer_id is None or from_id is None:
        raise ValueError("VK event не содержит peer_id/from_id")

    is_private = int(peer_id) == int(from_id)
    chat_name = "private" if is_private else f"chat_{peer_id}"

    return IncomingEvent(
        chat_id=int(peer_id),
        user_id=int(from_id),
        text=str(text),
        username=str(message.get("username") or f"id{from_id}"),
        chat_name=chat_name,
        is_private=is_private,
        platform="vk",
        raw_event_id=str(message.get("conversation_message_id") or message.get("id") or "unknown"),
        raw_payload=event,
    )
