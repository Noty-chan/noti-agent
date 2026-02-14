"""Mapper Telegram update -> IncomingEvent."""

from __future__ import annotations

from typing import Any

from noty.transport.types import IncomingEvent


def _first_non_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def map_telegram_update(update: dict[str, Any]) -> IncomingEvent:
    message = update.get("message") or update.get("edited_message")
    if not message:
        raise ValueError("Telegram update не содержит message/edited_message")

    chat = message.get("chat", {})
    sender = message.get("from", {})
    chat_type = chat.get("type", "private")
    is_private = chat_type == "private"

    chat_id = _first_non_none(chat.get("id"), sender.get("id"))
    user_id = _first_non_none(sender.get("id"), chat.get("id"))
    text = message.get("text") or message.get("caption") or ""
    username = sender.get("username") or sender.get("first_name") or "unknown"
    chat_name = chat.get("title") or chat.get("username") or username
    raw_event_id = str(_first_non_none(update.get("update_id"), message.get("message_id"), "unknown"))

    if chat_id is None or user_id is None:
        raise ValueError("Telegram update не содержит chat_id/user_id")

    return IncomingEvent(
        chat_id=int(chat_id),
        user_id=int(user_id),
        text=str(text),
        username=str(username),
        chat_name=str(chat_name),
        is_private=is_private,
        platform="telegram",
        raw_event_id=raw_event_id,
        raw_payload=update,
    )
