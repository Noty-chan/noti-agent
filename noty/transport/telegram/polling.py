"""Polling/Webhook ingestion для Telegram."""

from __future__ import annotations

from typing import Any, Iterable

from noty.transport.telegram.client import TelegramClient


class TelegramPolling:
    def __init__(self, client: TelegramClient, polling_timeout: int = 20):
        self.client = client
        self.polling_timeout = polling_timeout
        self._offset: int | None = None

    def poll(self) -> list[dict[str, Any]]:
        updates = self.client.get_updates(offset=self._offset, timeout=self.polling_timeout)
        if updates:
            self._offset = int(updates[-1]["update_id"]) + 1
        return updates


class TelegramWebhookReceiver:
    """Контейнер для вебхука: отдаёт принятый апдейт как итерируемый источник."""

    def __init__(self, update_payload: dict[str, Any]):
        self.update_payload = update_payload

    def poll(self) -> Iterable[dict[str, Any]]:
        return [self.update_payload]
