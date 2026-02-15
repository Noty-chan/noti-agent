import json
import time
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


def test_collect_full_logs_combines_sections(tmp_path: Path, monkeypatch):
    runtime_log = tmp_path / "runtime.log"
    interactions_dir = tmp_path / "interactions"
    thoughts_dir = tmp_path / "thoughts"
    actions_dir = tmp_path / "actions"
    interactions_dir.mkdir()
    thoughts_dir.mkdir()
    actions_dir.mkdir()

    runtime_log.write_text("runtime-line", encoding="utf-8")
    (interactions_dir / "2026-01-01.jsonl").write_text('{"direction":"incoming"}\n', encoding="utf-8")
    (thoughts_dir / "2026-01-01.jsonl").write_text('{"thought":"x"}\n', encoding="utf-8")
    (actions_dir / "2026-01-01.jsonl").write_text('{"action":"ban"}\n', encoding="utf-8")

    monkeypatch.setattr(web_panel, "RUNTIME_LOG_PATH", runtime_log)
    monkeypatch.setattr(web_panel, "INTERACTIONS_LOG_DIR", interactions_dir)
    monkeypatch.setattr(web_panel, "THOUGHTS_LOG_DIR", thoughts_dir)
    monkeypatch.setattr(web_panel, "ACTIONS_LOG_DIR", actions_dir)

    aggregated = web_panel._collect_full_logs()
    assert "Runtime log" in aggregated
    assert "Interactions log" in aggregated
    assert "Thoughts log" in aggregated
    assert "Actions log" in aggregated


def test_chat_simulator_send_stores_history(monkeypatch):
    class DummyBot:
        def handle_message(self, event):
            return {"status": "responded", "text": f"echo:{event['text']}"}

    simulator = web_panel.LocalPanelChatSimulator(history_limit=2)
    monkeypatch.setattr(simulator, "_build_bot", lambda: DummyBot())

    result1 = simulator.send("привет", chat_id=1, user_id=2, username="u")
    result2 = simulator.send("еще", chat_id=1, user_id=2, username="u")
    result3 = simulator.send("третье", chat_id=1, user_id=2, username="u")

    assert result1["status"] == "responded"
    assert result2["text"] == "echo:еще"
    assert result3["text"] == "echo:третье"

    history = simulator.history()
    assert len(history) == 2
    assert history[0]["user"] == "еще"
    assert history[1]["noty"] == "echo:третье"



def test_chat_simulator_enqueue_send_updates_job_and_history(monkeypatch):
    class DummyBot:
        def handle_message(self, event):
            return {"status": "responded", "text": f"echo:{event['text']}"}

    simulator = web_panel.LocalPanelChatSimulator(history_limit=5)
    monkeypatch.setattr(simulator, "_build_bot", lambda: DummyBot())

    request_id = simulator.enqueue_send("привет", chat_id=10, user_id=22, username="u")

    for _ in range(100):
        status_payload = simulator.status(request_id)
        if status_payload and status_payload.get("status") == "responded":
            break
        time.sleep(0.01)
    else:
        raise AssertionError("Фоновая задача не завершилась")

    assert status_payload is not None
    assert status_payload["status"] == "responded"
    assert status_payload["result"]["text"] == "echo:привет"

    history = simulator.history()
    matching = [row for row in history if row.get("request_id") == request_id]
    assert len(matching) == 1
    assert matching[0]["status"] == "responded"
    assert matching[0]["noty"] == "echo:привет"


def test_chat_health_snapshot_contains_status_counters(monkeypatch):
    class DummyBot:
        def handle_message(self, event):
            return {"status": "ignored", "text": ""}

    simulator = web_panel.LocalPanelChatSimulator(history_limit=5)
    monkeypatch.setattr(simulator, "_build_bot", lambda: DummyBot())

    request_id = simulator.enqueue_send("test", chat_id=11, user_id=33, username="u")
    for _ in range(100):
        status_payload = simulator.status(request_id)
        if status_payload and status_payload.get("status") == "ignored":
            break
        time.sleep(0.01)
    health = simulator.health_snapshot()

    assert health["jobs_total"] >= 1
    assert health["statuses"]["ignored"] >= 1
    assert "avg_duration_ms" in health
