"""Кратковременное состояние с TTL для чатов и пользователей."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict


@dataclass
class SessionStateStore:
    ttl_seconds: int = 3600
    _store: Dict[str, Dict[str, Dict[str, Any]]] = field(default_factory=lambda: {"chat": {}, "user": {}, "flow": {}})

    VALID_NAMESPACES = {"chat", "user", "flow"}

    def _now(self) -> datetime:
        return datetime.now()

    def _expires_at(self) -> datetime:
        return self._now() + timedelta(seconds=self.ttl_seconds)

    def _ns(self, namespace: str) -> Dict[str, Dict[str, Any]]:
        if namespace not in self.VALID_NAMESPACES:
            raise ValueError(f"Unknown namespace: {namespace}")
        return self._store[namespace]

    def set(self, namespace: str, scope_id: str, payload: Dict[str, Any]) -> None:
        self._ns(namespace)[scope_id] = {
            "payload": payload,
            "expires_at": self._expires_at(),
        }

    def get(self, namespace: str, scope_id: str, default: Dict[str, Any] | None = None) -> Dict[str, Any] | None:
        self.cleanup_expired()
        data = self._ns(namespace).get(scope_id)
        if not data:
            return default
        return data["payload"]

    def touch(self, namespace: str, scope_id: str) -> None:
        ns_store = self._ns(namespace)
        if scope_id in ns_store:
            ns_store[scope_id]["expires_at"] = self._expires_at()

    def clear_scope(self, scope_id: str) -> int:
        removed = 0
        for namespace in self.VALID_NAMESPACES:
            if self._store[namespace].pop(scope_id, None) is not None:
                removed += 1
        return removed

    def cleanup_expired(self) -> int:
        now = self._now()
        removed = 0
        for namespace in self.VALID_NAMESPACES:
            expired = [key for key, data in self._store[namespace].items() if data["expires_at"] <= now]
            for key in expired:
                self._store[namespace].pop(key, None)
                removed += 1
        return removed

    def cleanup_expired_namespace(self, namespace: str) -> int:
        now = self._now()
        ns_store = self._ns(namespace)
        expired = [key for key, data in ns_store.items() if data["expires_at"] <= now]
        for key in expired:
            ns_store.pop(key, None)
        return len(expired)

    def size(self) -> int:
        self.cleanup_expired()
        return sum(len(namespace_store) for namespace_store in self._store.values())
