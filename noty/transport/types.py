"""Транспортные контракты входящих событий."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(slots=True)
class IncomingEvent:
    """Унифицированное событие для downstream-логики."""

    chat_id: int
    user_id: int
    text: str
    username: str
    chat_name: str
    is_private: bool
    platform: str
    raw_event_id: str
    raw_payload: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_incoming_event(event: IncomingEvent | Mapping[str, Any]) -> IncomingEvent:
    """Нормализует вход до IncomingEvent."""

    if isinstance(event, IncomingEvent):
        return event

    payload = dict(event)
    required = {
        "chat_id",
        "user_id",
        "text",
        "username",
        "chat_name",
        "is_private",
        "platform",
        "raw_event_id",
    }
    missing = required.difference(payload)
    if missing:
        raise ValueError(f"В событии отсутствуют поля: {sorted(missing)}")

    return IncomingEvent(
        chat_id=int(payload["chat_id"]),
        user_id=int(payload["user_id"]),
        text=str(payload["text"]),
        username=str(payload["username"]),
        chat_name=str(payload["chat_name"]),
        is_private=bool(payload["is_private"]),
        platform=str(payload["platform"]),
        raw_event_id=str(payload["raw_event_id"]),
        raw_payload=payload.get("raw_payload"),
    )
