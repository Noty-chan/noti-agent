"""Безопасное выполнение tool-calls с подтверждением и аудитом."""

from __future__ import annotations

import hashlib
import inspect
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict


class SafeToolExecutor:
    @staticmethod
    def _is_personality_action(function_name: str) -> bool:
        return "personality" in function_name.lower()

    def __init__(self, owner_id: int, actions_log_dir: str = "./noty/data/logs/actions"):
        self.owner_id = owner_id
        self.pending_confirmations: Dict[str, Dict[str, Any]] = {}
        self.confirmed_results: Dict[str, Dict[str, Any]] = {}
        self.tools_registry: Dict[str, Dict[str, Any]] = {}
        self.execution_log: list[Dict[str, Any]] = []
        self.actions_log_dir = Path(actions_log_dir)
        self.actions_log_dir.mkdir(parents=True, exist_ok=True)
        self.audit_log_file = self.actions_log_dir / "dangerous_audit.jsonl"

    def register_tool(
        self,
        name: str,
        function: Callable[..., Any],
        requires_owner: bool = False,
        requires_private: bool = False,
        requires_confirmation: bool = False,
        description: str = "",
        risk_level: str = "low",
    ):
        self.tools_registry[name] = {
            "function": function,
            "requires_owner": requires_owner,
            "requires_private": requires_private,
            "requires_confirmation": requires_confirmation,
            "description": description,
            "risk_level": risk_level,
        }

    def register_personality_tool(
        self,
        name: str,
        function: Callable[..., Any],
        description: str = "",
        risk_level: str = "critical",
    ):
        self.register_tool(
            name=name,
            function=function,
            requires_owner=True,
            requires_confirmation=True,
            description=description,
            risk_level=risk_level,
        )

    def execute(self, tool_call: Dict[str, Any], user_id: int, chat_id: int, is_private: bool) -> Dict[str, Any]:
        function_name = tool_call.get("name")
        if function_name not in self.tools_registry:
            return {"status": "validation_error", "message": f"Инструмент {function_name} не найден."}

        tool_info = self.tools_registry[function_name]
        arguments = tool_call.get("arguments", {})
        if not isinstance(arguments, dict):
            return {"status": "validation_error", "message": "Аргументы инструмента должны быть объектом."}

        if tool_info["requires_owner"] and user_id != self.owner_id:

            return {"status": "forbidden", "message": "Недостаточно прав."}

            if self._is_personality_action(function_name):
                self._audit_dangerous_action(
                    function_name=function_name,
                    user_id=user_id,
                    chat_id=chat_id,
                    arguments=arguments,
                    stage="access_denied",
                    risk_level=tool_info.get("risk_level", "high"),
                    error="owner_only",
                )

        if tool_info["requires_private"] and not is_private:
            return {"status": "forbidden", "message": "Инструмент доступен только в ЛС."}

        if tool_info["requires_confirmation"]:
            confirmation_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
            self.pending_confirmations[confirmation_id] = {
                "tool_call": tool_call,
                "user_id": user_id,
                "chat_id": chat_id,
                "expires_at": time.time() + 60,
            }
            if self._is_personality_action(function_name) or tool_info.get("risk_level") in {"high", "critical"}:
                self._audit_dangerous_action(
                    function_name=function_name,
                    user_id=user_id,
                    chat_id=chat_id,
                    arguments=arguments,
                    stage="confirmation_requested",
                    risk_level=tool_info.get("risk_level", "low"),
                )
            return {
                "status": "awaiting_confirmation",
                "confirmation_id": confirmation_id,
                "message": f"⚠️ Подтверди: /confirm {confirmation_id}",
            }

        try:
            result = self._execute_safely(tool_info["function"], arguments)
            self._log_execution(function_name, user_id, chat_id, arguments, result, "success")
            if self._is_personality_action(function_name) or tool_info.get("risk_level") in {"high", "critical"}:
                self._audit_dangerous_action(
                    function_name=function_name,
                    user_id=user_id,
                    chat_id=chat_id,
                    arguments=arguments,
                    stage="executed_without_confirmation",
                    risk_level=tool_info.get("risk_level", "low"),
                )
            return {"status": "success", "result": result, "message": f"✅ Выполнено: {function_name}"}
        except Exception as exc:  # noqa: BLE001

            self._log_execution(function_name, user_id, chat_id, arguments, None, "runtime_error", str(exc))
            if tool_info.get("risk_level") in {"high", "critical"}:

            self._log_execution(function_name, user_id, chat_id, arguments, None, "error", str(exc))
            if self._is_personality_action(function_name) or tool_info.get("risk_level") in {"high", "critical"}:

                self._audit_dangerous_action(
                    function_name=function_name,
                    user_id=user_id,
                    chat_id=chat_id,
                    arguments=arguments,
                    stage="execution_error",
                    risk_level=tool_info.get("risk_level", "low"),
                    error=str(exc),
                )
            return {"status": "runtime_error", "message": f"Ошибка: {exc}"}

    def confirm_pending(self, confirmation_id: str) -> Dict[str, Any]:
        if confirmation_id in self.confirmed_results:
            return {
                **self.confirmed_results[confirmation_id],
                "idempotent": True,
            }

        pending = self.pending_confirmations.get(confirmation_id)
        if not pending:
            return {"status": "validation_error", "message": "Подтверждение не найдено."}
        if time.time() > pending["expires_at"]:
            del self.pending_confirmations[confirmation_id]
            return {"status": "validation_error", "message": "Время подтверждения истекло."}

        tool_call = pending["tool_call"]
        tool_info = self.tools_registry[tool_call["name"]]
        if tool_info["requires_owner"] and pending["user_id"] != self.owner_id:
            self._audit_dangerous_action(
                function_name=tool_call["name"],
                user_id=pending["user_id"],
                chat_id=pending["chat_id"],
                arguments=tool_call.get("arguments", {}),
                stage="confirmed_access_denied",
                risk_level=tool_info.get("risk_level", "high"),
                error="owner_only",
            )
            del self.pending_confirmations[confirmation_id]
            return {"status": "error", "message": "Недостаточно прав."}

        try:
            result = self._execute_safely(tool_info["function"], tool_call.get("arguments", {}))
            self._log_execution(tool_call["name"], pending["user_id"], pending["chat_id"], tool_call.get("arguments", {}), result, "success_confirmed")
            if self._is_personality_action(tool_call["name"]) or tool_info.get("risk_level") in {"high", "critical"} or tool_info.get("requires_confirmation"):
                self._audit_dangerous_action(
                    function_name=tool_call["name"],
                    user_id=pending["user_id"],
                    chat_id=pending["chat_id"],
                    arguments=tool_call.get("arguments", {}),
                    stage="confirmed_and_executed",
                    risk_level=tool_info.get("risk_level", "low"),
                )
            del self.pending_confirmations[confirmation_id]
            response = {"status": "success", "result": result, "message": "✅ Подтверждено и выполнено"}
            self.confirmed_results[confirmation_id] = response
            return response
        except Exception as exc:  # noqa: BLE001
            self._log_execution(tool_call["name"], pending["user_id"], pending["chat_id"], tool_call.get("arguments", {}), None, "runtime_error", str(exc))
            self._audit_dangerous_action(
                function_name=tool_call["name"],
                user_id=pending["user_id"],
                chat_id=pending["chat_id"],
                arguments=tool_call.get("arguments", {}),
                stage="confirmed_execution_error",
                risk_level=tool_info.get("risk_level", "low"),
                error=str(exc),
            )
            response = {"status": "runtime_error", "message": f"Ошибка выполнения: {exc}"}
            self.confirmed_results[confirmation_id] = response
            return response

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

    def _audit_dangerous_action(
        self,
        function_name: str,
        user_id: int,
        chat_id: int,
        arguments: Dict[str, Any],
        stage: str,
        risk_level: str,
        error: str | None = None,
    ) -> None:
        audit_entry = {
            "timestamp": datetime.now().isoformat(),
            "function_name": function_name,
            "user_id": user_id,
            "chat_id": chat_id,
            "arguments": arguments,
            "risk_level": risk_level,
            "stage": stage,
            "error": error,
        }
        with open(self.audit_log_file, "a", encoding="utf-8") as file:
            file.write(json.dumps(audit_entry, ensure_ascii=False) + "\n")
