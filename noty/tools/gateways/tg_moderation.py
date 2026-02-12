"""Telegram-реализация шлюза модерации."""

from __future__ import annotations

from typing import Any

from .moderation import ModerationGateway, build_moderation_result


class TGModerationGateway(ModerationGateway):
    platform = "tg"

    def __init__(self, tg_client: Any):
        self.tg_client = tg_client

    def warn_user(self, chat_id: int, user_id: int, reason: str) -> dict[str, Any]:
        warning_note_id = self.tg_client.send_warning(chat_id=chat_id, user_id=user_id, reason=reason)
        return build_moderation_result(
            platform=self.platform,
            chat_id=chat_id,
            action="warn_user",
            platform_action_id=str(warning_note_id),
            reason=reason,
            user_id=user_id,
            warning_note_id=warning_note_id,
        )

    def mute_user(self, chat_id: int, user_id: int, minutes: int, reason: str) -> dict[str, Any]:
        until_ts = self.tg_client.restrict_user(chat_id=chat_id, user_id=user_id, minutes=minutes, reason=reason)
        return build_moderation_result(
            platform=self.platform,
            chat_id=chat_id,
            action="mute_user",
            platform_action_id=str(until_ts),
            reason=reason,
            user_id=user_id,
            muted_until=until_ts,
            minutes=minutes,
        )

    def ban_user(self, chat_id: int, user_id: int, reason: str) -> dict[str, Any]:
        ban_ok = self.tg_client.ban_user(chat_id=chat_id, user_id=user_id, reason=reason)
        action_id = f"ban:{chat_id}:{user_id}" if ban_ok else f"ban_failed:{chat_id}:{user_id}"
        return build_moderation_result(
            platform=self.platform,
            chat_id=chat_id,
            action="ban_user",
            platform_action_id=action_id,
            reason=reason,
            user_id=user_id,
            banned=bool(ban_ok),
        )

    def delete_message(self, chat_id: int, message_id: int) -> dict[str, Any]:
        deleted = self.tg_client.delete_message(chat_id=chat_id, message_id=message_id)
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
        deleted_count = self.tg_client.bulk_delete_messages(chat_id=chat_id, message_ids=message_ids)
        return build_moderation_result(
            platform=self.platform,
            chat_id=chat_id,
            action="bulk_delete_messages",
            platform_action_id=f"bulk:{chat_id}:{int(deleted_count)}",
            reason=None,
            message_ids=message_ids,
            deleted_count=int(deleted_count),
        )
