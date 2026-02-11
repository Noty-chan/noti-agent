"""Команды самоуправления Ноти."""


def sleep_mode(hours: float = 2.0) -> str:
    return f"Ноти уходит в сон на {hours} ч."


def wake_up() -> str:
    return "Ноти проснулась и готова работать."
