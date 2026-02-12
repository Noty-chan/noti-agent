"""Интерфейс шлюза модерации для платформенных провайдеров."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ModerationGateway(ABC):
    """Контракт модерации для конкретной платформы (VK/TG и др.)."""

    platform: str

    @abstractmethod
    def warn_user(self, chat_id: int, user_id: int, reason: str) -> dict[str, Any]:
        """Выдать предупреждение пользователю."""

    @abstractmethod
    def mute_user(self, chat_id: int, user_id: int, minutes: int, reason: str) -> dict[str, Any]:
        """Ограничить пользователя по времени."""

    @abstractmethod
    def ban_user(self, chat_id: int, user_id: int, reason: str) -> dict[str, Any]:
        """Забанить пользователя."""

    @abstractmethod
    def delete_message(self, chat_id: int, message_id: int) -> dict[str, Any]:
        """Удалить одно сообщение."""

    @abstractmethod
    def bulk_delete_messages(self, chat_id: int, message_ids: list[int]) -> dict[str, Any]:
        """Массово удалить сообщения."""



def build_moderation_result(*, platform: str, chat_id: int, action: str, platform_action_id: str, reason: str | None = None, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "platform": platform,
        "chat_id": chat_id,
        "action": action,
        "status": "success",
        "platform_action_id": platform_action_id,
        "reason": reason,
    }
    payload.update(extra)
    return payload
