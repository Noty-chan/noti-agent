"""Маппинг VK событий в унифицированные DTO."""

from __future__ import annotations

from typing import Any, Dict

from noty.core.events import IncomingEvent as CoreIncomingEvent
from noty.transport.types import IncomingEvent

VK_MESSAGE_NEW = "message_new"


def map_vk_event(event: dict[str, Any]) -> IncomingEvent:
    """Новый контракт transport-layer: VK event -> transport.types.IncomingEvent."""
    if event.get("type") != VK_MESSAGE_NEW:
        raise ValueError(f"Неподдерживаемый VK event type: {event.get('type')}")

    payload = event.get("object", {})
    message = payload.get("message", payload)

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
        raw_event_id=str(message.get("conversation_message_id") or message.get("id") or event.get("event_id") or "unknown"),
        raw_payload=event,
    )


def map_vk_update_to_incoming_event(update: Dict[str, Any]) -> CoreIncomingEvent | None:
    """Legacy-совместимый маппер для core.events.IncomingEvent."""
    if update.get("type") != VK_MESSAGE_NEW:
        return None

    message = (update.get("object") or {}).get("message", {})
    text = (message.get("text") or "").strip()
    if not text:
        return None

    peer_id = message.get("peer_id")
    from_id = message.get("from_id")
    if peer_id is None or from_id is None:
        return None

    return CoreIncomingEvent(
        platform="vk",
        chat_id=int(peer_id),
        user_id=int(from_id),
        text=text,
        update_id=update.get("event_id") or message.get("conversation_message_id") or message.get("id"),
        chat_name="private" if int(peer_id) == int(from_id) else f"chat_{peer_id}",
        username=message.get("username") or f"id{from_id}",
    )
