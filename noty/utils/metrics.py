"""Сбор метрик latency/token-cost/errors и фильтрации."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Dict


@dataclass
class MetricsCollector:
    """Лёгкий in-memory сборщик метрик для отладки и мониторинга."""

    counters: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    scoped_counters: Dict[str, Dict[str, int]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))
    timings: Dict[str, Dict[str, float]] = field(default_factory=lambda: defaultdict(lambda: {"count": 0, "total": 0.0, "max": 0.0}))
    token_usage: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    scoped_token_usage: Dict[str, Dict[str, int]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))

    def inc(self, key: str, value: int = 1, scope: str | None = None) -> None:
        self.counters[key] += value
        if scope:
            self.scoped_counters[scope][key] += value

    def record_tokens(self, usage: Dict[str, Any] | None, scope: str | None = None) -> None:
        if not usage:
            return
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            raw = usage.get(key, 0)
            try:
                amount = int(raw)
            except (TypeError, ValueError):
                continue
            self.token_usage[key] += amount
            if scope:
                self.scoped_token_usage[scope][key] += amount

    def time_block(self, metric_name: str):
        collector = self

        class _Timer:
            def __enter__(self):
                self.start = perf_counter()
                return self

            def __exit__(self, exc_type, exc, tb):
                elapsed = perf_counter() - self.start
                bucket = collector.timings[metric_name]
                bucket["count"] += 1
                bucket["total"] += elapsed
                bucket["max"] = max(bucket["max"], elapsed)

        return _Timer()

    def snapshot(self) -> Dict[str, Any]:
        avg_timings = {}
        for metric, values in self.timings.items():
            count = values["count"] or 1
            avg_timings[metric] = {
                "count": int(values["count"]),
                "avg_seconds": round(values["total"] / count, 4),
                "max_seconds": round(values["max"], 4),
            }
        return {
            "global": {
                "counters": dict(self.counters),
                "token_usage": dict(self.token_usage),
            },
            "scope": {
                scope: {
                    "counters": dict(counters),
                    "token_usage": dict(self.scoped_token_usage.get(scope, {})),
                }
                for scope, counters in self.scoped_counters.items()
            },
            "timings": avg_timings,
        }
