"""Ротация API-ключей OpenRouter с обработкой ошибок и rate-limit."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any, Dict, List, Optional

from openai import OpenAI


class APIRotator:
    """Умная ротация между API-ключами OpenRouter."""

    def __init__(
        self,
        api_keys: List[str],
        backend: str = "openai",
        app_referer: Optional[str] = None,
        app_title: str = "Noty",
    ):
        self.api_keys = api_keys
        self.backend = backend
        self.app_referer = app_referer
        self.app_title = app_title
        self.current_idx = 0
        self.failed_keys = set()
        self.key_stats = {key: {"calls": 0, "errors": 0, "latency_ms": []} for key in api_keys}
        self.degraded_keys: dict[str, int] = {}
        self.max_acceptable_latency_ms = 2500
        self.degraded_cooldown_calls = 2
        self.logger = logging.getLogger(__name__)

    def _build_default_headers(self) -> Dict[str, str]:
        """Возвращает рекомендуемые OpenRouter-заголовки для идентификации приложения."""
        headers: Dict[str, str] = {}
        if self.app_referer:
            headers["HTTP-Referer"] = self.app_referer
        if self.app_title:
            headers["X-Title"] = self.app_title
        return headers

    def _maybe_recover_degraded(self) -> None:
        recovered: list[str] = []
        for key, remaining_calls in self.degraded_keys.items():
            if remaining_calls <= 0:
                recovered.append(key)
            else:
                self.degraded_keys[key] = remaining_calls - 1
        for key in recovered:
            self.degraded_keys.pop(key, None)

    def _get_next_key(self) -> Optional[str]:
        attempts = 0
        max_attempts = len(self.api_keys)
        self._maybe_recover_degraded()
        while attempts < max_attempts:
            key = self.api_keys[self.current_idx % len(self.api_keys)]
            self.current_idx += 1
            if key not in self.failed_keys and key not in self.degraded_keys:
                return key
            attempts += 1
        self.failed_keys.clear()
        if self.degraded_keys:
            self.degraded_keys.clear()
        return self.api_keys[0] if self.api_keys else None

    def _mark_key_degraded(self, key: str) -> None:
        self.degraded_keys[key] = self.degraded_cooldown_calls

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
                call_params: Dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    **kwargs,
                }
                if tools:
                    call_params["tools"] = tools

                self.logger.info("LLM call started: backend=%s model=%s", self.backend, model)
                started_at = perf_counter()
                response = self._call_backend(api_key=api_key, call_params=call_params)
                latency_ms = (perf_counter() - started_at) * 1000
                self.key_stats[api_key]["calls"] += 1
                self.key_stats[api_key]["latency_ms"].append(round(latency_ms, 2))
                if latency_ms > self.max_acceptable_latency_ms:
                    self._mark_key_degraded(api_key)

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
                self.logger.warning("LLM call failed for key idx=%s: %s", self.current_idx, error_msg)
                self.key_stats[api_key]["errors"] += 1
                self._mark_key_degraded(api_key)
                if "rate_limit" in error_msg or "429" in error_msg:
                    self.failed_keys.add(api_key)
                    continue
                if "401" in error_msg or "invalid" in error_msg:
                    self.failed_keys.add(api_key)
                    continue
                continue
        raise RuntimeError("Все попытки вызова API провалились")

    def _call_backend(self, api_key: str, call_params: Dict[str, Any]):
        default_headers = self._build_default_headers()
        if self.backend == "litellm":
            from litellm import completion

            if default_headers:
                call_params = {**call_params, "extra_headers": default_headers}
            return completion(api_key=api_key, base_url="https://openrouter.ai/api/v1", **call_params)

        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key, default_headers=default_headers)
        return client.chat.completions.create(**call_params)

    def structured_call(
        self,
        response_model: Any,
        messages: List[Dict[str, str]],
        model: str = "meta-llama/llama-3.1-70b-instruct",
        **kwargs: Any,
    ) -> Any:
        """Структурированный вызов через Instructor поверх OpenAI-клиента."""
        api_key = self._get_next_key()
        if not api_key:
            raise RuntimeError("Нет доступного API ключа для structured_call")

        import instructor

        client = instructor.patch(
            OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key,
                default_headers=self._build_default_headers(),
            )
        )
        self.logger.info("Structured LLM call started: model=%s", model)
        return client.chat.completions.create(response_model=response_model, model=model, messages=messages, **kwargs)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_keys": len(self.api_keys),
            "failed_keys": len(self.failed_keys),
            "degraded_keys": list(self.degraded_keys.keys()),
            "key_stats": self.key_stats,
        }
