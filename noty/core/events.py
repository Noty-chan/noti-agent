"""DTO входящих событий, scope-утилиты и JSONL-логирование."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping


def build_scope(platform: str, chat_id: int, thread_id: int | None = None) -> str:
    """Формирует ключ контекста: platform:chat_id[:thread_id]."""
    base = f"{platform}:{chat_id}"
    return base if thread_id is None else f"{base}:{thread_id}"


def enrich_event_scope(event: Mapping[str, Any], default_platform: str = "unknown") -> Dict[str, Any]:
    """Добавляет в payload нормализованную платформу и scope."""
    payload = dict(event)
    platform = str(payload.get("platform") or default_platform)
    chat_id = int(payload["chat_id"])
    thread_id = payload.get("thread_id")
    if thread_id is not None:
        thread_id = int(thread_id)

    payload["platform"] = platform
    payload["scope"] = build_scope(platform=platform, chat_id=chat_id, thread_id=thread_id)
    return payload


@dataclass(slots=True)
class IncomingEvent:
    """Legacy-совместимый формат события для core-обработчиков."""

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
    """Логирует входящие и исходящие события в дневные jsonl-файлы."""

    def __init__(self, logs_dir: str = "./noty/data/logs/interactions"):
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def _file_for_today(self) -> Path:
        return self.logs_dir / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"

    @staticmethod
    def _as_payload(event: Any) -> Dict[str, Any]:
        if hasattr(event, "to_dict"):
            return event.to_dict()
        if is_dataclass(event):
            return asdict(event)
        if isinstance(event, Mapping):
            return dict(event)
        return {"repr": repr(event)}

    def log_incoming(self, event: Any) -> None:
        self._append(
            {
                "timestamp": datetime.now().isoformat(),
                "direction": "incoming",
                "event": self._as_payload(event),
            }
        )

    def log_outgoing(self, event: Any, payload: Dict[str, Any]) -> None:
        self._append(
            {
                "timestamp": datetime.now().isoformat(),
                "direction": "outgoing",
                "event": self._as_payload(event),
                "payload": payload,
            }
        )

    def _append(self, entry: Dict[str, Any]) -> None:
        with open(self._file_for_today(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
