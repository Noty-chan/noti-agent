"""VK-реализация шлюза модерации."""

from __future__ import annotations

from typing import Any

from .moderation import ModerationGateway, build_moderation_result


class VKModerationGateway(ModerationGateway):
    platform = "vk"

    def __init__(self, vk_client: Any):
        self.vk_client = vk_client

    def warn_user(self, chat_id: int, user_id: int, reason: str) -> dict[str, Any]:
        warning_id = self.vk_client.warn_user(chat_id=chat_id, user_id=user_id, reason=reason)
        return build_moderation_result(
            platform=self.platform,
            chat_id=chat_id,
            action="warn_user",
            platform_action_id=str(warning_id),
            reason=reason,
            user_id=user_id,
        )

    def mute_user(self, chat_id: int, user_id: int, minutes: int, reason: str) -> dict[str, Any]:
        mute_id = self.vk_client.mute_user(chat_id=chat_id, user_id=user_id, minutes=minutes, reason=reason)
        return build_moderation_result(
            platform=self.platform,
            chat_id=chat_id,
            action="mute_user",
            platform_action_id=str(mute_id),
            reason=reason,
            user_id=user_id,
            minutes=minutes,
        )

    def ban_user(self, chat_id: int, user_id: int, reason: str) -> dict[str, Any]:
        ban_id = self.vk_client.ban_user(chat_id=chat_id, user_id=user_id, reason=reason)
        return build_moderation_result(
            platform=self.platform,
            chat_id=chat_id,
            action="ban_user",
            platform_action_id=str(ban_id),
            reason=reason,
            user_id=user_id,
        )

    def delete_message(self, chat_id: int, message_id: int) -> dict[str, Any]:
        deleted = self.vk_client.delete_message(chat_id=chat_id, message_id=message_id)
        action_id = f"msg:{message_id}" if deleted else f"failed:{message_id}"
        return build_moderation_result(
            platform=self.platform,
            chat_id=chat_id,
            action="delete_message",
            platform_action_id=action_id,
            reason=None,
            message_id=message_id,
            deleted=bool(deleted),
        )

    def bulk_delete_messages(self, chat_id: int, message_ids: list[int]) -> dict[str, Any]:
        deleted_ids = self.vk_client.bulk_delete_messages(chat_id=chat_id, message_ids=message_ids)
        return build_moderation_result(
            platform=self.platform,
            chat_id=chat_id,
            action="bulk_delete_messages",
            platform_action_id=f"bulk:{chat_id}:{len(deleted_ids)}",
            reason=None,
            message_ids=message_ids,
            deleted_ids=deleted_ids,
            deleted_count=len(deleted_ids),
        )
