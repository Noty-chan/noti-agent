"""Routing входящих платформенных событий в единый IncomingEvent контракт."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol

import yaml

from noty.transport.telegram.client import TelegramClient
from noty.transport.telegram.mapper import map_telegram_update
from noty.transport.telegram.polling import TelegramPolling, TelegramWebhookReceiver
from noty.transport.types import IncomingEvent, normalize_incoming_event
from noty.transport.vk.client import VKAPIClient
from noty.transport.vk.mapper import map_vk_event
from noty.transport.vk.state_store import VKStateStore, run_with_backoff


class EventSource(Protocol):
    def poll(self) -> Iterable[dict[str, Any]]:
        ...


@dataclass(slots=True)
class PlatformAdapter:
    platform: str
    source: EventSource
    mapper: Any

    def iter_events(self) -> Iterable[IncomingEvent]:
        for raw in self.source.poll():
            yield normalize_incoming_event(self.mapper(raw))


class TransportRouter:
    def __init__(self, adapters: list[PlatformAdapter]):
        self.adapters = adapters

    @staticmethod
    def make_routing_key(event: IncomingEvent) -> str:
        return f"{event.platform}:{event.chat_id}:{event.user_id}"

    def iter_events(self) -> Iterable[IncomingEvent]:
        for adapter in self.adapters:
            yield from adapter.iter_events()




class _StaticEventSource:
    """Источник событий для тестов/локального режима без реального poller-а."""

    def __init__(self, events: list[dict[str, Any]] | None = None):
        self.events = events or []

    def poll(self) -> list[dict[str, Any]]:
        return self.events

class VKLongPollSource:
    def __init__(self, client: VKAPIClient, state_store: VKStateStore, wait: int = 25):
        self.client = client
        self.state_store = state_store
        self.wait = wait
        self.server_info = run_with_backoff(self.client.get_longpoll_server)

    def poll(self) -> list[dict[str, Any]]:
        ts = self.state_store.get_longpoll_ts() or str(self.server_info["ts"])
        response = run_with_backoff(
            lambda: self.client.poll_events(
                server=self.server_info["server"],
                key=self.server_info["key"],
                ts=ts,
                wait=self.wait,
            )
        )
        new_ts = str(response.get("ts", ts))
        self.state_store.set_longpoll_ts(new_ts)
        return response.get("updates", [])


class VKWebhookEventSource:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload

    def poll(self) -> list[dict[str, Any]]:
        return [self.payload]


def load_transport_config(path: str | Path = "noty/config/bot_config.yaml") -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def create_transport_router(config_path: str | Path = "noty/config/bot_config.yaml") -> TransportRouter:
    cfg = load_transport_config(config_path)
    transport_cfg = cfg.get("transport", {})
    active_platforms = transport_cfg.get("active_platforms")

    if not active_platforms:
        fallback_platform = cfg.get("bot", {}).get("platform")
        active_platforms = [fallback_platform] if fallback_platform else []

    adapters: list[PlatformAdapter] = []
    for platform in active_platforms:
        if platform == "vk":
            vk_mode = transport_cfg.get("mode", "dry_run")
            vk_token = transport_cfg.get("vk_token", "")
            vk_group_id = int(transport_cfg.get("vk_group_id", 0) or 0)

            if vk_mode == "vk_longpoll" and vk_token and vk_group_id:
                client = VKAPIClient(
                    token=vk_token,
                    group_id=vk_group_id,
                    api_version=transport_cfg.get("vk_api_version", "5.199"),
                    timeout_seconds=int(transport_cfg.get("timeout_seconds", 25)),
                )
                state_store = VKStateStore(
                    state_path=transport_cfg.get("state_path", "./noty/data/vk_state.json"),
                    dedup_cache_size=int(transport_cfg.get("dedup_cache_size", 5000)),
                )
                source = VKLongPollSource(client=client, state_store=state_store, wait=int(transport_cfg.get("wait", 25)))
            elif vk_mode == "vk_webhook":
                source = VKWebhookEventSource(transport_cfg.get("vk_webhook_update", {}))
            else:
                source = _StaticEventSource()

            adapters.append(PlatformAdapter(platform="vk", source=source, mapper=map_vk_event))
            continue

        if platform == "telegram":
            tg_cfg = transport_cfg.get("telegram", {})
            mode = tg_cfg.get("mode", "polling")

            if mode == "polling":
                token = tg_cfg.get("bot_token", "")
                if token:
                    source: EventSource = TelegramPolling(TelegramClient(token=token))
                else:
                    source = _StaticEventSource()
            elif mode == "webhook":
                source = TelegramWebhookReceiver(tg_cfg.get("webhook_update", {}))
            else:
                raise ValueError(f"Неизвестный telegram mode: {mode}")

            adapters.append(PlatformAdapter(platform="telegram", source=source, mapper=map_telegram_update))
            continue

        raise ValueError(f"Неизвестная платформа в config: {platform}")

    return TransportRouter(adapters)
