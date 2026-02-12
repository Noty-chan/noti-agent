"""Постобработка ответа с учётом стратегии монолога."""

from __future__ import annotations

from typing import Any, Dict, List


class ResponseProcessor:
    def __init__(self):
        self.default_strategy: Dict[str, Any] = {
            "name": "balanced",
            "sarcasm_level": 0.4,
            "response_style": "balanced",
            "max_sentences": 4,
            "allowed_tool_risk": ["low", "medium"],
            "require_confirmation_escalation": False,
        }

    @staticmethod
    def _sanitize_style(text: str, strategy: Dict[str, Any]) -> str:
        cleaned = " ".join(part.strip() for part in text.splitlines() if part.strip())
        max_sentences = max(int(strategy.get("max_sentences", 4)), 1)
        parts = [p.strip() for p in cleaned.replace("!", ".").replace("?", ".").split(".") if p.strip()]
        limited = ". ".join(parts[:max_sentences]).strip()
        if not limited:
            return ""
        if not limited.endswith("."):
            limited += "."
        return limited

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

    def process(
        self,
        llm_response: Dict[str, Any],
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
