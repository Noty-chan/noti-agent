"""VK Long Poll transport-цикл."""

from __future__ import annotations

import logging
import random
from typing import Any, Dict

from noty.core.bot import NotyBot
from noty.transport.vk.client import VKAPIClient
from noty.transport.vk.mapper import map_vk_update_to_incoming_event
from noty.transport.vk.state_store import VKStateStore, run_with_backoff

logger = logging.getLogger(__name__)


class VKLongPollTransport:
    def __init__(self, client: VKAPIClient, bot: NotyBot, state_store: VKStateStore):
        self.client = client
        self.bot = bot
        self.state_store = state_store

    def run_forever(self) -> None:
        logger.info("Запуск VK longpoll transport")
        server_info = run_with_backoff(self.client.get_longpoll_server)
        ts = self.state_store.get_longpoll_ts() or str(server_info["ts"])

        while True:
            poll_response = run_with_backoff(
                lambda: self.client.poll_events(
                    server=server_info["server"],
                    key=server_info["key"],
                    ts=ts,
                )
            )
            ts = str(poll_response.get("ts", ts))
            self.state_store.set_longpoll_ts(ts)

            for update in poll_response.get("updates", []):
                self._process_update(update)

    def _process_update(self, update: Dict[str, Any]) -> None:
        event = map_vk_update_to_incoming_event(update)
        if not event:
            return
        if event.update_id is not None and self.state_store.is_processed(event.update_id):
            logger.debug("Скип дубликата update_id=%s", event.update_id)
            return

        result = self.bot.handle_message(event)
        if result.get("status") == "responded":
            random_id = random.randint(1, 2_147_483_647)
            run_with_backoff(lambda: self.client.send_message(event.chat_id, result["text"], random_id))

        if event.update_id is not None:
            self.state_store.mark_processed(event.update_id)
