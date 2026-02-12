"""Обработчик webhook-режима VK."""

from __future__ import annotations

import random
from typing import Any, Dict

from noty.core.bot import NotyBot
from noty.transport.vk.client import VKAPIClient
from noty.transport.vk.mapper import map_vk_update_to_incoming_event
from noty.transport.vk.state_store import VKStateStore, run_with_backoff


class VKWebhookHandler:
    def __init__(self, client: VKAPIClient, bot: NotyBot, state_store: VKStateStore, confirmation_token: str | None = None):
        self.client = client
        self.bot = bot
        self.state_store = state_store
        self.confirmation_token = confirmation_token

    def handle_update(self, payload: Dict[str, Any]) -> str:
        if payload.get("type") == "confirmation" and self.confirmation_token:
            return self.confirmation_token

        event = map_vk_update_to_incoming_event(payload)
        if not event:
            return "ok"

        if event.update_id is not None and self.state_store.is_processed(event.update_id):
            return "ok"

        result = self.bot.handle_message(event)
        if result.get("status") == "responded":
            random_id = random.randint(1, 2_147_483_647)
            run_with_backoff(lambda: self.client.send_message(event.chat_id, result["text"], random_id))

        if event.update_id is not None:
            self.state_store.mark_processed(event.update_id)
        return "ok"
