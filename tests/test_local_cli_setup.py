from pathlib import Path

from noty import cli


def test_setup_command_creates_env_from_template(tmp_path, monkeypatch):
    config_dir = tmp_path / "noty" / "config"
    config_dir.mkdir(parents=True)

    template = config_dir / ".env.example"
    target = config_dir / ".env"
    template.write_text("VK_TOKEN=\n", encoding="utf-8")

    monkeypatch.setattr(cli, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "ENV_TEMPLATE_PATH", template)
    monkeypatch.setattr(cli, "ENV_PATH", target)

    code = cli.setup_command(install_deps=False)

    assert code == 0
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "VK_TOKEN=\n"


def test_setup_command_fails_without_template(tmp_path, monkeypatch):
    config_dir = tmp_path / "noty" / "config"
    config_dir.mkdir(parents=True)

    template = config_dir / ".env.example"
    target = config_dir / ".env"

    monkeypatch.setattr(cli, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "ENV_TEMPLATE_PATH", template)
    monkeypatch.setattr(cli, "ENV_PATH", target)

    code = cli.setup_command(install_deps=False)

    assert code == 1
    assert not target.exists()


def test_run_command_passes_log_args_to_main(tmp_path, monkeypatch):
    config_dir = tmp_path / "noty" / "config"
    config_dir.mkdir(parents=True)

    bot_config = config_dir / "bot_config.yaml"
    bot_config.write_text("transport:\n  mode: dry_run\n", encoding="utf-8")

    api_keys = config_dir / "api_keys.json"
    api_keys.write_text('{"openrouter_keys": []}', encoding="utf-8")

    env_path = config_dir / ".env"
    env_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(cli, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cli, "BOT_CONFIG_PATH", bot_config)
    monkeypatch.setattr(cli, "API_KEYS_PATH", api_keys)
    monkeypatch.setattr(cli, "ENV_PATH", env_path)

    calls = []

    class Result:
        returncode = 0

    def fake_run(cmd, cwd, check):
        calls.append((cmd, cwd, check))
        return Result()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    code = cli.run_command(mode="dry_run", log_level="DEBUG", log_file="./noty/data/noty.log")

    assert code == 0
    assert calls
    assert calls[0][0] == [
        cli.sys.executable,
        "main.py",
        "--mode",
        "dry_run",
        "--log-level",
        "DEBUG",
        "--log-file",
        "./noty/data/noty.log",
    ]
