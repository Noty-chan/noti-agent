"""CLI для локального запуска и первичной настройки Noty без Docker."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "noty" / "config"
ENV_TEMPLATE_PATH = CONFIG_DIR / ".env.example"
ENV_PATH = CONFIG_DIR / ".env"
BOT_CONFIG_PATH = CONFIG_DIR / "bot_config.yaml"
API_KEYS_PATH = CONFIG_DIR / "api_keys.json"


def _print_status(title: str, ok: bool, details: str) -> None:
    icon = "[OK]" if ok else "[WARN]"
    print(f"{icon} {title}: {details}")


def _in_venv() -> bool:
    return getattr(sys, "base_prefix", sys.prefix) != sys.prefix


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError(
            "PyYAML не установлен. Выполни 'python -m noty.cli setup' или 'pip install -r requirements.txt'."
        ) from exc

    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _load_api_keys(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh) or {}
    return payload.get("openrouter_keys", [])


def setup_command(install_deps: bool = True) -> int:
    print("== Noty локальный setup ==")

    py_ok = sys.version_info >= (3, 10)
    _print_status("Python", py_ok, f"{sys.version.split()[0]} (требуется >= 3.10)")
    if not py_ok:
        return 1

    in_venv = _in_venv()
    _print_status("Virtualenv", in_venv, "venv активирован" if in_venv else "venv не активирован")

    if not ENV_TEMPLATE_PATH.exists():
        _print_status("ENV template", False, f"не найден: {ENV_TEMPLATE_PATH}")
        return 1

    if ENV_PATH.exists():
        _print_status("ENV", True, f"уже существует: {ENV_PATH}")
    else:
        ENV_PATH.write_text(ENV_TEMPLATE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        _print_status("ENV", True, f"создан из шаблона: {ENV_PATH}")

    if install_deps:
        print("Устанавливаю зависимости из requirements.txt...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(PROJECT_ROOT / "requirements.txt")],
            cwd=PROJECT_ROOT,
            check=False,
        )
        if result.returncode != 0:
            _print_status("Dependencies", False, "установка завершилась с ошибкой")
            return result.returncode
        _print_status("Dependencies", True, "зависимости установлены")
    else:
        _print_status("Dependencies", True, "пропущено (--skip-install)")

    print("Setup завершён. Дальше: python -m noty.cli run")
    return 0


def _health_status(config: dict[str, Any], log_level: str | None = None, log_file: str | None = None) -> None:
    print("== Health check ==")
    transport_cfg = config.get("transport", {})
    mode = transport_cfg.get("mode", "dry_run")
    active_platforms = transport_cfg.get("active_platforms") or [config.get("bot", {}).get("platform", "vk")]

    _print_status("Config", BOT_CONFIG_PATH.exists(), str(BOT_CONFIG_PATH))
    _print_status("Env file", ENV_PATH.exists(), str(ENV_PATH))
    _print_status("API keys", API_KEYS_PATH.exists(), str(API_KEYS_PATH))

    if API_KEYS_PATH.exists():
        keys = _load_api_keys(API_KEYS_PATH)
        _print_status("LLM keys", bool(keys), f"кол-во ключей: {len(keys)}")

    _print_status("Transport mode", True, mode)
    _print_status("Active platforms", True, ", ".join(active_platforms))

    logging_cfg = config.get("logging", {})
    resolved_level = (log_level or logging_cfg.get("level") or "INFO").upper()
    resolved_file = log_file or logging_cfg.get("file") or "stdout only"
    _print_status("Log level", True, resolved_level)
    _print_status("Log file", True, str(resolved_file))

    vk_required = "vk" in active_platforms and mode in {"vk_longpoll", "vk_webhook"}
    if vk_required:
        vk_token_ok = bool(transport_cfg.get("vk_token"))
        vk_group_ok = bool(transport_cfg.get("vk_group_id"))
        _print_status("VK token", vk_token_ok, "обязателен в текущем режиме")
        _print_status("VK group id", vk_group_ok, "обязателен в текущем режиме")

    tg_cfg = transport_cfg.get("telegram", {})
    tg_enabled = "telegram" in active_platforms
    tg_token_ok = bool(tg_cfg.get("bot_token"))
    if tg_enabled:
        _print_status("Telegram token", tg_token_ok, "опционально для first-run")


def run_command(mode: str | None = None, log_level: str | None = None, log_file: str | None = None) -> int:
    if not BOT_CONFIG_PATH.exists():
        _print_status("Config", False, f"не найден: {BOT_CONFIG_PATH}")
        return 1

    try:
        config = _load_yaml(BOT_CONFIG_PATH)
    except RuntimeError as exc:
        _print_status("Config parse", False, str(exc))
        return 1
    _health_status(config, log_level=log_level, log_file=log_file)

    cmd = [sys.executable, "main.py"]
    if mode:
        cmd.extend(["--mode", mode])
    if log_level:
        cmd.extend(["--log-level", log_level])
    if log_file:
        cmd.extend(["--log-file", log_file])

    print("== Запуск Noty ==")
    print("Подсказка: команда `run` запускает только бот-процесс. Web-панель запускается отдельно через `python -m noty.cli panel`.")
    return subprocess.run(cmd, cwd=PROJECT_ROOT, check=False).returncode


def _is_port_busy(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


def panel_command(host: str = "127.0.0.1", port: int = 8765, reload_enabled: bool = False) -> int:
    try:
        import uvicorn
        from noty.config import web_panel
    except ImportError:
        _print_status("Web panel", False, "uvicorn/fastapi не установлены. Установи зависимости: pip install -r requirements.txt")
        return 1

    if not getattr(web_panel, "FASTAPI_AVAILABLE", False):
        _print_status("Web panel", False, "fastapi не установлена в окружении")
        return 1

    if _is_port_busy(host, port):
        _print_status(
            "Web panel",
            False,
            (
                f"порт {host}:{port} уже занят. Останови предыдущий процесс панели "
                "или запусти с другим портом: python -m noty.cli panel --port 8766"
            ),
        )
        return 1

    print(f"== Запуск web-панели Noty: http://{host}:{port} ==")
    uvicorn.run("noty.config.web_panel:app", host=host, port=port, reload=reload_enabled)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Noty local CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    setup_parser = subparsers.add_parser("setup", help="первичная подготовка окружения")
    setup_parser.add_argument("--skip-install", action="store_true", help="пропустить pip install")

    run_parser = subparsers.add_parser("run", help="локальный запуск Noty")
    run_parser.add_argument("--mode", choices=["vk_longpoll", "vk_webhook", "dry_run"], default=None)
    run_parser.add_argument("--log-level", default=None, help="уровень логирования (DEBUG/INFO/WARNING/ERROR)")
    run_parser.add_argument("--log-file", default=None, help="путь к файлу логов (например ./noty/data/noty.log)")

    panel_parser = subparsers.add_parser("panel", help="запуск localhost web-панели конфигурации")
    panel_parser.add_argument("--host", default="127.0.0.1")
    panel_parser.add_argument("--port", type=int, default=8765)
    panel_parser.add_argument(
        "--reload",
        action="store_true",
        help="автоперезагрузка web-панели при изменении исходников (режим разработки)",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "setup":
        code = setup_command(install_deps=not args.skip_install)
        raise SystemExit(code)

    if args.command == "run":
        code = run_command(mode=args.mode, log_level=args.log_level, log_file=args.log_file)
        raise SystemExit(code)

    if args.command == "panel":
        code = panel_command(host=args.host, port=args.port, reload_enabled=args.reload)
        raise SystemExit(code)


if __name__ == "__main__":
    main()
