"""Небольшой CLI-терминал для настройки характера и промптов Ноти."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


DEFAULT_CONFIG = Path("./noty/config/persona_prompt_config.json")
DEFAULT_PROMPTS_DIR = Path("./noty/prompts")


def _load_config(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Конфиг не найден: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _save_config(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def cmd_show(args: argparse.Namespace) -> None:
    cfg = _load_config(Path(args.config))
    print(json.dumps(cfg, ensure_ascii=False, indent=2))


def cmd_set(args: argparse.Namespace) -> None:
    cfg = _load_config(Path(args.config))
    value: object = args.value
    if args.value_type == "float":
        value = float(args.value)
    elif args.value_type == "int":
        value = int(args.value)
    elif args.value_type == "json":
        value = json.loads(args.value)

    ptr = cfg
    parts = args.key.split(".")
    for part in parts[:-1]:
        if part not in ptr or not isinstance(ptr[part], dict):
            ptr[part] = {}
        ptr = ptr[part]
    ptr[parts[-1]] = value
    _save_config(Path(args.config), cfg)
    print(f"OK: {args.key}={value}")


def cmd_edit_prompt(args: argparse.Namespace) -> None:
    prompt_file = DEFAULT_PROMPTS_DIR / args.file
    if not prompt_file.exists():
        raise FileNotFoundError(f"Файл промпта не найден: {prompt_file}")
    prompt_file.write_text(args.text, encoding="utf-8")
    print(f"OK: обновлен {prompt_file}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Терминал настройки Ноти")
    sub = parser.add_subparsers(required=True)

    show = sub.add_parser("show", help="Показать текущий persona/prompt конфиг")
    show.add_argument("--config", default=str(DEFAULT_CONFIG))
    show.set_defaults(func=cmd_show)

    set_cmd = sub.add_parser("set", help="Изменить поле конфига по dotted-path")
    set_cmd.add_argument("key", help="Например: persona_adaptation_policy.reason")
    set_cmd.add_argument("value")
    set_cmd.add_argument("--value-type", choices=["str", "float", "int", "json"], default="str")
    set_cmd.add_argument("--config", default=str(DEFAULT_CONFIG))
    set_cmd.set_defaults(func=cmd_set)

    edit = sub.add_parser("edit-prompt", help="Заменить содержимое prompt-файла")
    edit.add_argument("file", choices=["base_core.txt", "safety_rules.txt"])
    edit.add_argument("text")
    edit.set_defaults(func=cmd_edit_prompt)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
