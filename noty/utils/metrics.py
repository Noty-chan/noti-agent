"""Сбор метрик latency/token-cost/errors и фильтрации."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from statistics import quantiles
from time import perf_counter
from typing import Any, Dict


@dataclass
class MetricsCollector:
    """Лёгкий in-memory сборщик метрик для отладки и мониторинга."""

    counters: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    scoped_counters: Dict[str, Dict[str, int]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))
    timings: Dict[str, Dict[str, float]] = field(default_factory=lambda: defaultdict(lambda: {"count": 0, "total": 0.0, "max": 0.0}))
    timing_samples: Dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    stage_platform_timings: Dict[str, Dict[str, list[float]]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(list)))
    token_usage: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    scoped_token_usage: Dict[str, Dict[str, int]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))
    stage_platform_token_cost_usd: Dict[str, Dict[str, float]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(float)))

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

    def record_token_cost(self, amount_usd: float | int | str, *, stage: str, platform: str) -> None:
        try:
            amount = float(amount_usd)
        except (TypeError, ValueError):
            return
        if amount < 0:
            return
        self.stage_platform_token_cost_usd[stage][platform] += amount

    def time_block(self, metric_name: str, *, stage: str | None = None, platform: str | None = None):
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
                collector.timing_samples[metric_name].append(elapsed)
                if stage and platform:
                    collector.stage_platform_timings[stage][platform].append(elapsed)

        return _Timer()

    @staticmethod
    def _percentile(data: list[float], percentile: float) -> float:
        if not data:
            return 0.0
        if len(data) == 1:
            return data[0]
        if percentile == 50:
            qs = quantiles(data, n=2, method="inclusive")
            return qs[0]
        if percentile == 95:
            qs = quantiles(data, n=100, method="inclusive")
            return qs[94]
        raise ValueError(f"Unsupported percentile: {percentile}")

    def _build_stage_platform_series(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        stages = set(self.stage_platform_timings) | set(self.stage_platform_token_cost_usd)
        for stage in stages:
            stage_item: Dict[str, Any] = {}
            platforms = set(self.stage_platform_timings.get(stage, {})) | set(self.stage_platform_token_cost_usd.get(stage, {}))
            for platform in platforms:
                samples = self.stage_platform_timings.get(stage, {}).get(platform, [])
                count = len(samples)
                avg = (sum(samples) / count) if count else 0.0
                stage_item[platform] = {
                    "count": count,
                    "avg_seconds": round(avg, 4),
                    "p50_seconds": round(self._percentile(samples, 50), 4),
                    "p95_seconds": round(self._percentile(samples, 95), 4),
                    "token_cost_usd": round(self.stage_platform_token_cost_usd.get(stage, {}).get(platform, 0.0), 6),
                }
            result[stage] = stage_item
        return result


    def respond_rate_alert(self, responded: int, total: int, target_rate: float = 0.2, tolerance: float = 0.05) -> Dict[str, Any] | None:
        if total <= 0:
            return None
        rate = responded / total
        lower = target_rate - tolerance
        upper = target_rate + tolerance
        if lower <= rate <= upper:
            return None
        reason = "перефильтрация" if rate < lower else "недофильтрация"
        return {
            "status": "alert",
            "reason": reason,
            "respond_rate": round(rate, 4),
            "target": target_rate,
            "tolerance": tolerance,
            "bounds": {"lower": round(lower, 4), "upper": round(upper, 4)},
        }

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
            "series": {
                "stage_platform": self._build_stage_platform_series(),
            },
        }
