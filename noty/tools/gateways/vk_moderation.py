"""VK-реализация шлюза модерации."""

from __future__ import annotations

from typing import Any

from .moderation import ModerationGateway


class VKModerationGateway(ModerationGateway):
    platform = "vk"

    def __init__(self, vk_client: Any):
        self.vk_client = vk_client

    def warn_user(self, chat_id: int, user_id: int, reason: str) -> dict[str, Any]:
        warning_id = self.vk_client.warn_user(chat_id=chat_id, user_id=user_id, reason=reason)
        return {
            "platform": self.platform,
            "chat_id": chat_id,
            "user_id": user_id,
            "warning_id": warning_id,
            "reason": reason,
        }

    def mute_user(self, chat_id: int, user_id: int, minutes: int, reason: str) -> dict[str, Any]:
        mute_id = self.vk_client.mute_user(chat_id=chat_id, user_id=user_id, minutes=minutes, reason=reason)
        return {
            "platform": self.platform,
            "chat_id": chat_id,
            "user_id": user_id,
            "mute_id": mute_id,
            "minutes": minutes,
            "reason": reason,
        }

    def ban_user(self, chat_id: int, user_id: int, reason: str) -> dict[str, Any]:
        ban_id = self.vk_client.ban_user(chat_id=chat_id, user_id=user_id, reason=reason)
        return {
            "platform": self.platform,
            "chat_id": chat_id,
            "user_id": user_id,
            "ban_id": ban_id,
            "reason": reason,
        }

    def delete_message(self, chat_id: int, message_id: int) -> dict[str, Any]:
        deleted = self.vk_client.delete_message(chat_id=chat_id, message_id=message_id)
        return {
            "platform": self.platform,
            "chat_id": chat_id,
            "message_id": message_id,
            "deleted": bool(deleted),
        }

    def bulk_delete_messages(self, chat_id: int, message_ids: list[int]) -> dict[str, Any]:
        deleted_ids = self.vk_client.bulk_delete_messages(chat_id=chat_id, message_ids=message_ids)
        return {
            "platform": self.platform,
            "chat_id": chat_id,
            "message_ids": message_ids,
            "deleted_ids": deleted_ids,
            "deleted_count": len(deleted_ids),
        }
