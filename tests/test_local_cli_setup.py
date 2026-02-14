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
