"""Клиент VK API для longpoll/webhook transport."""

from __future__ import annotations

import json
from typing import Any, Dict
from urllib.parse import urlencode
from urllib.request import urlopen


class VKAPIClient:
    def __init__(self, token: str, group_id: int, api_version: str = "5.199", timeout_seconds: int = 25):
        self.token = token
        self.group_id = group_id
        self.api_version = api_version
        self.timeout_seconds = timeout_seconds

    def call_method(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            **params,
            "access_token": self.token,
            "v": self.api_version,
        }
        url = f"https://api.vk.com/method/{method}?{urlencode(payload)}"
        with urlopen(url, timeout=self.timeout_seconds) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
        if "error" in data:
            raise RuntimeError(f"VK API error: {data['error']}")
        return data["response"]

    def get_longpoll_server(self) -> Dict[str, Any]:
        return self.call_method("groups.getLongPollServer", {"group_id": self.group_id})

    def poll_events(self, server: str, key: str, ts: str, wait: int = 25) -> Dict[str, Any]:
        query = urlencode({"act": "a_check", "key": key, "ts": ts, "wait": wait})
        url = f"{server}?{query}"
        with urlopen(url, timeout=self.timeout_seconds + wait) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))

    def send_message(self, peer_id: int, text: str, random_id: int) -> Dict[str, Any]:
        return self.call_method(
            "messages.send",
            {
                "peer_id": peer_id,
                "message": text,
                "random_id": random_id,
            },
        )
