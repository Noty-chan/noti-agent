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

