from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from noty.core.context_manager import DynamicContextBuilder
from noty.memory.recent_days_memory import RecentDaysMemory
from noty.memory.sqlite_db import SQLiteDBManager
from noty.utils.metrics import MetricsCollector


class _DummyEncoder:
    def encode(self, text: str):
        return [float(len(text) or 1)]


class _DummyEmbeddingFilter:
    def __init__(self):
        self.encoder = _DummyEncoder()


def test_recent_days_memory_decay_prioritizes_fresh_facts(tmp_path: Path):
    db = SQLiteDBManager(str(tmp_path / "decay.db"))
    memory = RecentDaysMemory(db_manager=db, days_window=7, decay_lambda=0.8)

    old_ts = (datetime.now() - timedelta(days=3)).isoformat()
    new_ts = (datetime.now() - timedelta(hours=2)).isoformat()
    memory.remember_message(platform="vk", chat_id=1, user_id=10, text="старый факт", timestamp=old_ts)
    memory.remember_message(platform="vk", chat_id=1, user_id=10, text="свежий факт", timestamp=new_ts)

    facts = memory.get_context_facts(platform="vk", chat_id=1, limit=2, min_weight=0.01)

    assert len(facts) == 2
    assert facts[0]["text"] == "свежий факт"
    assert facts[0]["weight"] > facts[1]["weight"]


def test_recent_days_memory_integrates_into_context_and_metrics(tmp_path: Path):
    db = SQLiteDBManager(str(tmp_path / "context.db"))
    metrics = MetricsCollector()
    memory = RecentDaysMemory(db_manager=db, days_window=5, maintenance_interval_minutes=1)

    builder = DynamicContextBuilder(
        db_manager=db,
        embedding_filter=_DummyEmbeddingFilter(),
        recent_days_memory=memory,
        metrics=metrics,
    )
    context = builder.build_context(platform="vk", chat_id=33, current_message="запомни этот фон", user_id=7)

    assert context["sources"]["rolling_recent_days"] >= 1
    assert context["metadata"]["rolling_memory_share"] > 0
    assert "rolling-memory" in context["summary"]

    snapshot = metrics.snapshot()
    scope = snapshot["scope"]["vk:33"]
    assert scope["counters"]["rolling_memory_context_facts"] >= 1


def test_recent_days_memory_maintenance_cleans_old(tmp_path: Path):
    db = SQLiteDBManager(str(tmp_path / "maintenance.db"))
    memory = RecentDaysMemory(db_manager=db, days_window=1, decay_lambda=0.4, maintenance_interval_minutes=1)

    old_ts = (datetime.now() - timedelta(days=5)).isoformat()
    memory.remember_message(platform="vk", chat_id=55, user_id=1, text="очень старое", timestamp=old_ts)

    executed = memory.run_maintenance_if_due()
    facts = memory.get_context_facts(platform="vk", chat_id=55, limit=5)

    assert executed is True
    assert facts == []
