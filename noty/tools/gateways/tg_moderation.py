"""Telegram-реализация шлюза модерации."""

from __future__ import annotations

from typing import Any

from .moderation import ModerationGateway


class TGModerationGateway(ModerationGateway):
    platform = "tg"

    def __init__(self, tg_client: Any):
        self.tg_client = tg_client

    def warn_user(self, chat_id: int, user_id: int, reason: str) -> dict[str, Any]:
        warning_note_id = self.tg_client.send_warning(chat_id=chat_id, user_id=user_id, reason=reason)
        return {
            "platform": self.platform,
            "chat_id": chat_id,
            "user_id": user_id,
            "warning_note_id": warning_note_id,
            "reason": reason,
        }

    def mute_user(self, chat_id: int, user_id: int, minutes: int, reason: str) -> dict[str, Any]:
        until_ts = self.tg_client.restrict_user(chat_id=chat_id, user_id=user_id, minutes=minutes, reason=reason)
        return {
            "platform": self.platform,
            "chat_id": chat_id,
            "user_id": user_id,
            "muted_until": until_ts,
            "minutes": minutes,
            "reason": reason,
        }

    def ban_user(self, chat_id: int, user_id: int, reason: str) -> dict[str, Any]:
        ban_ok = self.tg_client.ban_user(chat_id=chat_id, user_id=user_id, reason=reason)
        return {
            "platform": self.platform,
            "chat_id": chat_id,
            "user_id": user_id,
            "banned": bool(ban_ok),
            "reason": reason,
        }

    def delete_message(self, chat_id: int, message_id: int) -> dict[str, Any]:
        deleted = self.tg_client.delete_message(chat_id=chat_id, message_id=message_id)
        return {
            "platform": self.platform,
            "chat_id": chat_id,
            "message_id": message_id,
            "deleted": bool(deleted),
        }

    def bulk_delete_messages(self, chat_id: int, message_ids: list[int]) -> dict[str, Any]:
        deleted_count = self.tg_client.bulk_delete_messages(chat_id=chat_id, message_ids=message_ids)
        return {
            "platform": self.platform,
            "chat_id": chat_id,
            "message_ids": message_ids,
            "deleted_count": int(deleted_count),
        }
