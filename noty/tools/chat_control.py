"""Инструменты модерации поверх platform gateway + журнал действий."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .gateways.moderation import ModerationGateway
from .tool_executor import SafeToolExecutor


class ChatControlService:
    """Единый фасад модерации для tool-calls."""

    def __init__(self, gateway: ModerationGateway, actions_log_dir: str = "./noty/data/logs/actions"):
        self.gateway = gateway
        self.actions_log_dir = Path(actions_log_dir)
        self.actions_log_dir.mkdir(parents=True, exist_ok=True)

    def warn_user(self, chat_id: int, user_id: int, reason: str) -> dict[str, Any]:
        result = self.gateway.warn_user(chat_id=chat_id, user_id=user_id, reason=reason)
        self._log_action("warn", chat_id=chat_id, user_id=user_id, reason=reason, gateway_result=result)
        return result

    def mute_user(self, chat_id: int, user_id: int, minutes: int, reason: str) -> dict[str, Any]:
        result = self.gateway.mute_user(chat_id=chat_id, user_id=user_id, minutes=minutes, reason=reason)
        self._log_action(
            "mute",
            chat_id=chat_id,
            user_id=user_id,
            reason=reason,
            minutes=minutes,
            gateway_result=result,
        )
        return result

    def ban_user(self, chat_id: int, user_id: int, reason: str) -> dict[str, Any]:
        result = self.gateway.ban_user(chat_id=chat_id, user_id=user_id, reason=reason)
        self._log_action("ban", chat_id=chat_id, user_id=user_id, reason=reason, gateway_result=result)
        return result

    def delete_message(self, chat_id: int, message_id: int) -> dict[str, Any]:
        result = self.gateway.delete_message(chat_id=chat_id, message_id=message_id)
        self._log_action("delete_message", chat_id=chat_id, message_id=message_id, gateway_result=result)
        return result

    def bulk_delete_messages(self, chat_id: int, message_ids: list[int]) -> dict[str, Any]:
        result = self.gateway.bulk_delete_messages(chat_id=chat_id, message_ids=message_ids)
        self._log_action(
            "bulk_delete_messages",
            chat_id=chat_id,
            message_ids=message_ids,
            gateway_result=result,
        )
        return result

    def _log_action(self, action: str, **metadata: Any) -> None:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "platform": self.gateway.platform,
            "action": action,
            "metadata": metadata,
        }
        day_file = self.actions_log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        with open(day_file, "a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")


def register_chat_control_tools(executor: SafeToolExecutor, service: ChatControlService) -> None:
    """Регистрация chat-control tools с правилами безопасности."""
    executor.register_tool(
        "warn_user",
        service.warn_user,
        description="Предупредить пользователя",
        risk_level="medium",
    )
    executor.register_tool(
        "mute_user",
        service.mute_user,
        description="Замьютить пользователя на короткий срок",
        risk_level="medium",
    )
    executor.register_tool(
        "mute_user_long",
        service.mute_user,
        requires_owner=True,
        requires_confirmation=True,
        description="Длительный мут пользователя",
        risk_level="high",
    )
    executor.register_tool(
        "ban_user",
        service.ban_user,
        requires_owner=True,
        requires_confirmation=True,
        description="Забанить пользователя",
        risk_level="critical",
    )
    executor.register_tool(
        "delete_message",
        service.delete_message,
        description="Удалить сообщение",
        risk_level="medium",
    )
    executor.register_tool(
        "bulk_delete_messages",
        service.bulk_delete_messages,
        requires_owner=True,
        requires_confirmation=True,
        description="Массовое удаление сообщений",
        risk_level="high",
    )
