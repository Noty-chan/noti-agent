from pathlib import Path

from noty.memory.persona_profile import PersonaProfileManager
from noty.memory.sqlite_db import SQLiteDBManager
from noty.prompts.prompt_builder import ModularPromptBuilder


def test_persona_profile_update_and_fallback(tmp_path: Path):
    db = SQLiteDBManager(str(tmp_path / "noty.db"))
    manager = PersonaProfileManager(db_manager=db, min_profile_confidence=0.5)

    profile = manager.update_from_dialogue(
        user_id=1,
        chat_id=100,
        text="Пиши кратко и без сарказма, не говори про политику",
    )

    assert profile.response_depth_preference == "short"
    assert profile.sarcasm_tolerance <= 0.2
    assert "политику" in " ".join(profile.taboo_topics)
    assert manager.should_use_conservative_fallback(profile)


def test_prompt_has_persona_policy_layer(tmp_path: Path):
    prompts_dir = tmp_path / "prompts"
    cfg = tmp_path / "persona_prompt_config.json"
    cfg.write_text(
        '{"persona_adaptation_policy": {"version": 3, "reason": "a/b", "policy_text": "test policy"}}',
        encoding="utf-8",
    )

    builder = ModularPromptBuilder(str(prompts_dir), config_path=str(cfg))
    prompt = builder.build_full_prompt(context={"messages": [], "summary": ""}, persona_profile={"confidence": 0.2})

    assert "PERSONA ADAPTATION POLICY" in prompt
    assert "reason_for_change: a/b" in prompt
    assert "version: 3" in prompt
