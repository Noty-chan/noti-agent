"""Хранение offset/update_id и retry/backoff для VK transport."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Iterable


class VKStateStore:
    def __init__(self, state_path: str = "./noty/data/vk_state.json", dedup_cache_size: int = 5000):
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.dedup_cache_size = dedup_cache_size
        self._state = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"longpoll_ts": None, "processed_update_ids": []}
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _persist(self) -> None:
        self.state_path.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_longpoll_ts(self) -> str | None:
        return self._state.get("longpoll_ts")

    def set_longpoll_ts(self, ts: str | None) -> None:
        self._state["longpoll_ts"] = ts
        self._persist()

    def is_processed(self, update_id: int | str) -> bool:
        return str(update_id) in set(map(str, self._state.get("processed_update_ids", [])))

    def mark_processed(self, update_id: int | str) -> None:
        ids = [str(x) for x in self._state.get("processed_update_ids", [])]
        ids.append(str(update_id))
        self._state["processed_update_ids"] = ids[-self.dedup_cache_size :]
        self._persist()


def run_with_backoff(
    operation: Callable[[], Any],
    retries: int = 5,
    base_delay_seconds: float = 0.5,
    retryable_exceptions: Iterable[type[Exception]] = (Exception,),
) -> Any:
    attempt = 0
    while True:
        try:
            return operation()
        except tuple(retryable_exceptions):
            if attempt >= retries:
                raise
            delay = base_delay_seconds * (2**attempt)
            time.sleep(delay)
            attempt += 1
