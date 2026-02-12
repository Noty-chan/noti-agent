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
