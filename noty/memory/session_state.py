"""Кратковременное состояние с TTL для чатов и пользователей."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict


@dataclass
class SessionStateStore:
    ttl_seconds: int = 3600
    _store: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def _now(self) -> datetime:
        return datetime.now()

    def _expires_at(self) -> datetime:
        return self._now() + timedelta(seconds=self.ttl_seconds)

    def set(self, scope_id: str, payload: Dict[str, Any]) -> None:
        self._store[scope_id] = {
            "payload": payload,
            "expires_at": self._expires_at(),
        }

    def get(self, scope_id: str, default: Dict[str, Any] | None = None) -> Dict[str, Any] | None:
        self.cleanup_expired()
        data = self._store.get(scope_id)
        if not data:
            return default
        return data["payload"]

    def touch(self, scope_id: str) -> None:
        if scope_id in self._store:
            self._store[scope_id]["expires_at"] = self._expires_at()

    def cleanup_expired(self) -> int:
        now = self._now()
        expired = [key for key, data in self._store.items() if data["expires_at"] <= now]
        for key in expired:
            self._store.pop(key, None)
        return len(expired)

    def size(self) -> int:
        self.cleanup_expired()
        return len(self._store)
