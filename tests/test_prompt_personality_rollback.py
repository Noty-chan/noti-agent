from pathlib import Path

from noty.prompts.prompt_builder import ModularPromptBuilder


def test_personality_rollback_to_previous_version(tmp_path: Path):
    prompts_dir = tmp_path / "prompts"
    builder = ModularPromptBuilder(str(prompts_dir))

    v2 = builder.save_new_personality_version("v2", reason="test")
    builder.approve_personality_version(v2)
    v3 = builder.save_new_personality_version("v3", reason="test")
    builder.approve_personality_version(v3)

    rolled = builder.rollback_personality_version()
    assert rolled == v2
    current = (prompts_dir / "versions" / "current.txt").read_text(encoding="utf-8")
    assert current == "v2"
