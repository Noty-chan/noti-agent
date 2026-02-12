"""Минимальный клиент Telegram Bot API."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class TelegramClient:
    def __init__(self, token: str, timeout: int = 30):
        self._base_url = f"https://api.telegram.org/bot{token}"
        self._timeout = timeout

    def get_updates(self, offset: int | None = None, timeout: int = 20) -> list[dict[str, Any]]:
        params = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        url = f"{self._base_url}/getUpdates?{urlencode(params)}"
        with urlopen(url, timeout=self._timeout) as response:  # noqa: S310
            data = json.loads(response.read().decode("utf-8"))
        if not data.get("ok"):
            raise RuntimeError(f"Telegram getUpdates error: {data}")
        return data.get("result", [])

    def set_webhook(self, url: str) -> dict[str, Any]:
        body = urlencode({"url": url}).encode("utf-8")
        request = Request(f"{self._base_url}/setWebhook", data=body, method="POST")
        with urlopen(request, timeout=self._timeout) as response:  # noqa: S310
            data = json.loads(response.read().decode("utf-8"))
        if not data.get("ok"):
            raise RuntimeError(f"Telegram setWebhook error: {data}")
        return data
