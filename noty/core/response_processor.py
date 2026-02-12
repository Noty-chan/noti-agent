"""Постобработка ответа LLM: tool-calls и итоговый ответ пользователю."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List

from noty.tools.tool_executor import SafeToolExecutor


@dataclass
class ResponseProcessingResult:
    status: str
    text: str
    tools_used: List[str]
    tool_results: List[Dict[str, Any]]
    outcome: str


class ResponseProcessor:
    def __init__(self, tool_executor: SafeToolExecutor):
        self.tool_executor = tool_executor

    def process(
        self,
        llm_response: Dict[str, Any],
        *,
        user_id: int,
        chat_id: int,
        is_private: bool,
    ) -> ResponseProcessingResult:
        content = llm_response.get("content") or ""
        tool_calls = llm_response.get("tool_calls") or []

        if not tool_calls:
            return ResponseProcessingResult(
                status="responded",
                text=content,
                tools_used=[],
                tool_results=[],
                outcome="success",
            )

        tool_results: List[Dict[str, Any]] = []
        tools_used: List[str] = []

        for tool_call in tool_calls:
            normalized_tool_call = self._normalize_tool_call(tool_call)
            if not normalized_tool_call.get("name"):
                tool_results.append(
                    {
                        "name": "unknown",
                        "status": "validation_error",
                        "message": "Некорректный формат tool_call: отсутствует имя инструмента.",
                    }
                )
                continue

            result = self.tool_executor.execute(
                normalized_tool_call,
                user_id=user_id,
                chat_id=chat_id,
                is_private=is_private,
            )
            tool_results.append({"name": normalized_tool_call["name"], **result})
            tools_used.append(normalized_tool_call["name"])

        final_status = self._derive_status(tool_results)
        outcome = "success" if final_status in {"success", "awaiting_confirmation"} else "negative"

        return ResponseProcessingResult(
            status=final_status,
            text=self._build_user_text(content, tool_results),
            tools_used=tools_used,
            tool_results=tool_results,
            outcome=outcome,
        )

    @staticmethod
    def _normalize_tool_call(tool_call: Any) -> Dict[str, Any]:
        if isinstance(tool_call, dict):
            name = tool_call.get("name")
            arguments = tool_call.get("arguments", {})
        else:
            function = getattr(tool_call, "function", None)
            name = getattr(function, "name", None) or getattr(tool_call, "name", None)
            arguments = getattr(function, "arguments", None) or getattr(tool_call, "arguments", {})

        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError:
                arguments = {}

        if not isinstance(arguments, dict):
            arguments = {}

        return {"name": name, "arguments": arguments}

    @staticmethod
    def _derive_status(tool_results: List[Dict[str, Any]]) -> str:
        statuses = {item.get("status", "runtime_error") for item in tool_results}
        if "awaiting_confirmation" in statuses:
            return "awaiting_confirmation"
        if statuses and statuses.issubset({"success"}):
            return "success"
        if "forbidden" in statuses:
            return "forbidden"
        if "validation_error" in statuses:
            return "validation_error"
        return "runtime_error"

    @staticmethod
    def _build_user_text(content: str, tool_results: List[Dict[str, Any]]) -> str:
        messages = [item.get("message", "") for item in tool_results if item.get("message")]
        if content and messages:
            return f"{content}\n\n" + "\n".join(messages)
        if messages:
            return "\n".join(messages)
        return content
