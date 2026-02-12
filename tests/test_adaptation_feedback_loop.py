from pathlib import Path

from noty.core.adaptation_engine import AdaptationEngine
from noty.memory.relationship_manager import RelationshipManager
from noty.memory.sqlite_db import SQLiteDBManager
from noty.prompts.prompt_builder import ModularPromptBuilder


class DummyMem0:
    def recall(self, query: str, user_id: str, limit: int = 5):
        return []

    def remember(self, text: str, user_id: str, metadata=None):
        return None


def test_adaptation_engine_reduces_sarcasm_on_negative_streak():
    engine = AdaptationEngine()

    recommendation = engine.recommend(
        interaction_outcome="fail",
        user_feedback_signals={"sentiment": "negative"},
        relationship_trend={"score": -2, "positive_ratio": 0.3, "negative_streak": 3},
        filter_stats={"decider": {"respond_rate": 0.35}},
    )

    assert recommendation.preferred_tone == "dry"
    assert recommendation.sarcasm_level <= 0.2
    assert recommendation.rollback_required is True


def test_relationship_manager_tracks_tone_quality_stats(tmp_path: Path):
    db = tmp_path / "rel.db"
    manager = RelationshipManager(str(db), DummyMem0())

    manager.update_relationship(1, "u", "positive", tone_used="playful")
    manager.update_relationship(1, "u", "negative", tone_used="playful")
    manager.update_relationship(1, "u", "negative", tone_used="harsh")

    trend = manager.get_relationship_trend(1)
    assert trend["tone_success_stats"]["playful"] == 1
    assert trend["tone_fail_stats"]["playful"] == 1
    assert trend["tone_fail_stats"]["harsh"] == 1
    assert trend["negative_streak"] == 2


def test_prompt_builder_runtime_personality_modifiers(tmp_path: Path):
    prompts_dir = tmp_path / "prompts"
    builder = ModularPromptBuilder(str(prompts_dir))

    prompt = builder.build_full_prompt(
        context={"messages": [{"role": "user", "content": "привет"}]},
        runtime_modifiers={"preferred_tone": "dry", "sarcasm_level": 0.1, "response_rate_bias": -0.05},
    )

    assert "RUNTIME PERSONALITY MODIFIERS" in prompt
    assert "preferred_tone: dry" in prompt
    assert "sarcasm_level: 0.10" in prompt


def test_sqlite_prompt_versions_has_signal_source(tmp_path: Path):
    db_path = tmp_path / "noty.db"
    manager = SQLiteDBManager(str(db_path))

    conn = manager._connect()
    cols = {row[1] for row in conn.execute("PRAGMA table_info(prompt_versions)").fetchall()}
    conn.close()

    assert "signal_source" in cols
