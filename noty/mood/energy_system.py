"""Утилиты расчёта энергии и усталости."""


def energy_cost_by_action(action: str) -> int:
    mapping = {
        "short_reply": 1,
        "long_reply": 3,
        "tool_use": 2,
        "conflict": 4,
        "idle": 0,
    }
    return mapping.get(action, 1)
