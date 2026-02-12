"""Постобработка ответа: стратегия монолога + безопасные tool-calls."""

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
    def __init__(self, tool_executor: SafeToolExecutor | None = None):
        self.tool_executor = tool_executor
        self.default_strategy: Dict[str, Any] = {
            "name": "balanced",
            "sarcasm_level": 0.4,
            "response_style": "balanced",
            "max_sentences": 4,
            "allowed_tool_risk": ["low", "medium"],
            "require_confirmation_escalation": False,
        }

    def process(self, llm_response: Dict[str, Any], **kwargs):
        """Поддерживает два режима:
        1) strategy-only (возвращает dict) — для интеграции монолога;
        2) tool-execution (возвращает ResponseProcessingResult).
        """
        if "strategy" in kwargs or "tools_registry" in kwargs:
            strategy = kwargs.get("strategy")
            tools_registry = kwargs.get("tools_registry") or {}
            return self._process_strategy(llm_response, strategy=strategy, tools_registry=tools_registry)

        return self._process_execution(
            llm_response,
            user_id=int(kwargs["user_id"]),
            chat_id=int(kwargs["chat_id"]),
            is_private=bool(kwargs["is_private"]),
        )

    @staticmethod
    def _sanitize_style(text: str, strategy: Dict[str, Any]) -> str:
        cleaned = " ".join(part.strip() for part in text.splitlines() if part.strip())
        max_sentences = max(int(strategy.get("max_sentences", 4)), 1)
        parts = [p.strip() for p in cleaned.replace("!", ".").replace("?", ".").split(".") if p.strip()]
        limited = ". ".join(parts[:max_sentences]).strip()
        if not limited:
            return ""
        return limited if limited.endswith(".") else f"{limited}."

    @staticmethod
    def _resolve_sarcasm_prefix(strategy: Dict[str, Any]) -> str:
        sarcasm_level = float(strategy.get("sarcasm_level", 0.0))
        if sarcasm_level >= 0.8:
            return "Ну конечно"
        if sarcasm_level >= 0.5:
            return "Ладно"
        return ""

    @staticmethod
    def _is_tool_allowed(tool_name: str, allowed_tool_risk: List[str], tools_registry: Dict[str, Dict[str, Any]]) -> bool:
        tool_info = tools_registry.get(tool_name)
        if not tool_info:
            return False
        risk_level = tool_info.get("risk_level", "low")
        return risk_level in allowed_tool_risk

    def _process_strategy(
        self,
        llm_response: Dict[str, Any],
        *,
        strategy: Dict[str, Any] | None,
        tools_registry: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        active_strategy = strategy or self.default_strategy
        raw_text = llm_response.get("content", "")
        formatted_text = self._sanitize_style(raw_text, active_strategy)

        prefix = self._resolve_sarcasm_prefix(active_strategy)
        if prefix and formatted_text:
            formatted_text = f"{prefix}, {formatted_text[0].lower()}{formatted_text[1:]}"

        allowed_risks = active_strategy.get("allowed_tool_risk", ["low"])
        selected_tools = []
        for tool_call in llm_response.get("tool_calls", []) or []:
            tool_name = tool_call.get("name")
            if tool_name and self._is_tool_allowed(tool_name, allowed_risks, tools_registry):
                selected_tools.append(tool_call)

        return {
            "text": formatted_text or raw_text,
            "selected_tools": selected_tools,
            "confirmation_escalation": bool(active_strategy.get("require_confirmation_escalation", False)),
            "strategy_used": active_strategy,
        }

    def _process_execution(self, llm_response: Dict[str, Any], *, user_id: int, chat_id: int, is_private: bool) -> ResponseProcessingResult:
        content = llm_response.get("content") or ""
        tool_calls = llm_response.get("tool_calls") or []

        if not tool_calls:
            return ResponseProcessingResult("responded", content, [], [], "success")
        if not self.tool_executor:
            return ResponseProcessingResult("validation_error", content, [], [], "negative")

        tool_results: List[Dict[str, Any]] = []
        tools_used: List[str] = []

        for tool_call in tool_calls:
            normalized = self._normalize_tool_call(tool_call)
            if not normalized.get("name"):
                tool_results.append({"name": "unknown", "status": "validation_error", "message": "Некорректный format tool_call."})
                continue

            result = self.tool_executor.execute(normalized, user_id=user_id, chat_id=chat_id, is_private=is_private)
            tool_results.append({"name": normalized["name"], **result})
            tools_used.append(normalized["name"])

        final_status = self._derive_status(tool_results)
        outcome = "success" if final_status in {"success", "awaiting_confirmation"} else "negative"
        return ResponseProcessingResult(final_status, self._build_user_text(content, tool_results), tools_used, tool_results, outcome)

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
