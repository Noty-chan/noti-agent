import json
from pathlib import Path

import yaml

from noty.config import web_panel


def test_save_runtime_settings_updates_files(tmp_path: Path, monkeypatch):
    env_path = tmp_path / ".env"
    bot_cfg_path = tmp_path / "bot_config.yaml"
    persona_path = tmp_path / "persona_prompt_config.json"
    keys_path = tmp_path / "api_keys.json"

    env_path.write_text("LOCAL_PANEL_PASSWORD=secret\n", encoding="utf-8")
    bot_cfg_path.write_text("transport:\n  mode: dry_run\n", encoding="utf-8")
    persona_path.write_text("{}", encoding="utf-8")
    keys_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        web_panel,
        "PATHS",
        web_panel.RuntimePaths(env_path, bot_cfg_path, persona_path, keys_path),
    )

    web_panel.save_runtime_settings(
        {
            "vk_token": "vk-1",
            "vk_group_id": "42",
            "llm_backend": "litellm",
            "openrouter_api_key": "or-key",
            "sqlite_path": "./noty/data/test.db",
            "mem0_enabled": "true",
            "mem0_api_key": "m-key",
            "qdrant_url": "http://localhost:6333",
            "qdrant_api_key": "q-key",
            "local_panel_password": "new-secret",
            "prompt_config_json": '{"persona_adaptation_policy":{"version":2,"reason":"update"}}',
        }
    )

    env_data = web_panel._read_env(env_path)
    assert env_data["OPENROUTER_API_KEY"] == "or-key"
    assert env_data["LOCAL_PANEL_PASSWORD"] == "new-secret"

    bot_cfg = yaml.safe_load(bot_cfg_path.read_text(encoding="utf-8"))
    assert bot_cfg["transport"]["vk_group_id"] == 42
    assert bot_cfg["llm"]["backend"] == "litellm"

    persona_data = json.loads(persona_path.read_text(encoding="utf-8"))
    assert persona_data["persona_adaptation_policy"]["version"] == 2

    api_keys = json.loads(keys_path.read_text(encoding="utf-8"))
    assert api_keys["openrouter_keys"] == ["or-key"]


def test_get_panel_password_from_env(tmp_path: Path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("LOCAL_PANEL_PASSWORD=super-pass\n", encoding="utf-8")

    monkeypatch.setattr(
        web_panel,
        "PATHS",
        web_panel.RuntimePaths(env_path, tmp_path / "bot.yaml", tmp_path / "persona.json", tmp_path / "keys.json"),
    )

    assert web_panel._get_panel_password() == "super-pass"
