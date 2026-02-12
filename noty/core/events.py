
"""Утилиты нормализации событий и формирования scope-ключей."""

from __future__ import annotations

from typing import Any, Dict


def build_scope(platform: str, chat_id: int, thread_id: int | None = None) -> str:
    """Формирует единый ключ контекста: platform:chat_id[:thread_id]."""
    base = f"{platform}:{chat_id}"
    if thread_id is None:
        return base
    return f"{base}:{thread_id}"


def enrich_event_scope(event: Dict[str, Any], default_platform: str = "unknown") -> Dict[str, Any]:
    """Добавляет в событие вычисленный scope и нормализованную платформу."""
    platform = str(event.get("platform") or default_platform)
    chat_id = int(event["chat_id"])
    thread_id = event.get("thread_id")
    if thread_id is not None:
        thread_id = int(thread_id)

    enriched = dict(event)
    enriched["platform"] = platform
    enriched["scope"] = build_scope(platform=platform, chat_id=chat_id, thread_id=thread_id)
    return enriched


"""DTO входящих событий и JSONL-логирование взаимодействий."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


@dataclass(slots=True)
class IncomingEvent:
    """Единый формат события для NotyBot.handle_message."""

    platform: str
    chat_id: int
    user_id: int
    text: str
    update_id: int | str | None = None
    chat_name: str | None = None
    username: str | None = None
    relationship: Dict[str, Any] | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class InteractionJSONLLogger:
    """Полное логирование входящих/исходящих событий в daily jsonl."""

    def __init__(self, logs_dir: str = "./noty/data/logs/interactions"):
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def _file_for_today(self) -> Path:
        return self.logs_dir / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"

    def log_incoming(self, event: IncomingEvent) -> None:
        self._append(
            {
                "timestamp": datetime.now().isoformat(),
                "direction": "incoming",
                "event": event.to_dict(),
            }
        )

    def log_outgoing(self, event: IncomingEvent, payload: Dict[str, Any]) -> None:
        self._append(
            {
                "timestamp": datetime.now().isoformat(),
                "direction": "outgoing",
                "event": event.to_dict(),
                "payload": payload,
            }
        )

    def _append(self, entry: Dict[str, Any]) -> None:
        with open(self._file_for_today(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

