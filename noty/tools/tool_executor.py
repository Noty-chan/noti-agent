"""Безопасное выполнение tool-calls с подтверждением."""

from __future__ import annotations

import hashlib
import inspect
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict


class SafeToolExecutor:
    def __init__(self, owner_id: int, actions_log_dir: str = "./noty/data/logs/actions"):
        self.owner_id = owner_id
        self.pending_confirmations: Dict[str, Dict[str, Any]] = {}
        self.tools_registry: Dict[str, Dict[str, Any]] = {}
        self.execution_log: list[Dict[str, Any]] = []
        self.actions_log_dir = Path(actions_log_dir)
        self.actions_log_dir.mkdir(parents=True, exist_ok=True)

    def register_tool(
        self,
        name: str,
        function: Callable[..., Any],
        requires_owner: bool = False,
        requires_private: bool = False,
        requires_confirmation: bool = False,
        description: str = "",
    ):
        self.tools_registry[name] = {
            "function": function,
            "requires_owner": requires_owner,
            "requires_private": requires_private,
            "requires_confirmation": requires_confirmation,
            "description": description,
        }

    def execute(self, tool_call: Dict[str, Any], user_id: int, chat_id: int, is_private: bool) -> Dict[str, Any]:
        function_name = tool_call.get("name")
        if function_name not in self.tools_registry:
            return {"status": "error", "message": f"Инструмент {function_name} не найден."}

        tool_info = self.tools_registry[function_name]
        arguments = tool_call.get("arguments", {})

        if tool_info["requires_owner"] and user_id != self.owner_id:
            return {"status": "error", "message": "Недостаточно прав."}
        if tool_info["requires_private"] and not is_private:
            return {"status": "error", "message": "Инструмент доступен только в ЛС."}

        if tool_info["requires_confirmation"]:
            confirmation_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
            self.pending_confirmations[confirmation_id] = {
                "tool_call": tool_call,
                "user_id": user_id,
                "chat_id": chat_id,
                "expires_at": time.time() + 60,
            }
            return {
                "status": "awaiting_confirmation",
                "confirmation_id": confirmation_id,
                "message": f"⚠️ Подтверди: /confirm {confirmation_id}",
            }

        try:
            result = self._execute_safely(tool_info["function"], arguments)
            self._log_execution(function_name, user_id, chat_id, arguments, result, "success")
            return {"status": "success", "result": result, "message": f"✅ Выполнено: {function_name}"}
        except Exception as exc:  # noqa: BLE001
            self._log_execution(function_name, user_id, chat_id, arguments, None, "error", str(exc))
            return {"status": "error", "message": f"Ошибка: {exc}"}

    def confirm_pending(self, confirmation_id: str) -> Dict[str, Any]:
        pending = self.pending_confirmations.get(confirmation_id)
        if not pending:
            return {"status": "error", "message": "Подтверждение не найдено."}
        if time.time() > pending["expires_at"]:
            del self.pending_confirmations[confirmation_id]
            return {"status": "error", "message": "Время подтверждения истекло."}

        tool_call = pending["tool_call"]
        tool_info = self.tools_registry[tool_call["name"]]
        try:
            result = self._execute_safely(tool_info["function"], tool_call.get("arguments", {}))
            self._log_execution(tool_call["name"], pending["user_id"], pending["chat_id"], tool_call.get("arguments", {}), result, "success_confirmed")
            del self.pending_confirmations[confirmation_id]
            return {"status": "success", "result": result, "message": "✅ Подтверждено и выполнено"}
        except Exception as exc:  # noqa: BLE001
            self._log_execution(tool_call["name"], pending["user_id"], pending["chat_id"], tool_call.get("arguments", {}), None, "error", str(exc))
            return {"status": "error", "message": f"Ошибка выполнения: {exc}"}

    @staticmethod
    def _execute_safely(function: Callable[..., Any], arguments: Dict[str, Any]) -> Any:
        sig = inspect.signature(function)
        valid_args = {k: v for k, v in arguments.items() if k in sig.parameters}
        return function(**valid_args)

    def _log_execution(
        self,
        function_name: str,
        user_id: int,
        chat_id: int,
        arguments: Dict[str, Any],
        result: Any,
        status: str,
        error: str | None = None,
    ):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "function_name": function_name,
            "user_id": user_id,
            "chat_id": chat_id,
            "arguments": arguments,
            "result": result,
            "status": status,
            "error": error,
        }
        self.execution_log.append(entry)

        day_file = self.actions_log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        with open(day_file, "a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
