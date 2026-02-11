"""Ротация API-ключей OpenRouter с обработкой ошибок и rate-limit."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from openai import OpenAI


class APIRotator:
    """Умная ротация между API-ключами OpenRouter."""

    def __init__(self, api_keys: List[str]):
        self.api_keys = api_keys
        self.current_idx = 0
        self.failed_keys = set()
        self.key_stats = {key: {"calls": 0, "errors": 0} for key in api_keys}

    def _get_next_key(self) -> Optional[str]:
        attempts = 0
        max_attempts = len(self.api_keys)
        while attempts < max_attempts:
            key = self.api_keys[self.current_idx % len(self.api_keys)]
            self.current_idx += 1
            if key not in self.failed_keys:
                return key
            attempts += 1
        self.failed_keys.clear()
        return self.api_keys[0] if self.api_keys else None

    def call(
        self,
        messages: List[Dict[str, str]],
        model: str = "meta-llama/llama-3.1-70b-instruct",
        temperature: float = 0.7,
        max_tokens: int = 1000,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        for _ in range(len(self.api_keys)):
            api_key = self._get_next_key()
            if not api_key:
                raise RuntimeError("Все API ключи исчерпаны")
            try:
                client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
                call_params: Dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    **kwargs,
                }
                if tools:
                    call_params["tools"] = tools

                response = client.chat.completions.create(**call_params)
                self.key_stats[api_key]["calls"] += 1
                return {
                    "content": response.choices[0].message.content,
                    "tool_calls": response.choices[0].message.tool_calls,
                    "finish_reason": response.choices[0].finish_reason,
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens,
                    },
                }
            except Exception as exc:  # noqa: BLE001
                error_msg = str(exc).lower()
                if "rate_limit" in error_msg or "429" in error_msg:
                    self.failed_keys.add(api_key)
                    self.key_stats[api_key]["errors"] += 1
                    continue
                if "401" in error_msg or "invalid" in error_msg:
                    self.failed_keys.add(api_key)
                    continue
                raise
        raise RuntimeError("Все попытки вызова API провалились")

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_keys": len(self.api_keys),
            "failed_keys": len(self.failed_keys),
            "key_stats": self.key_stats,
        }
