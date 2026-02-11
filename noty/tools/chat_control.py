"""Инструменты модерации и управления чатом."""


def warn_user(user_id: int, reason: str) -> str:
    return f"Пользователь {user_id} предупреждён: {reason}"


def mute_user(user_id: int, minutes: int, reason: str) -> str:
    return f"Пользователь {user_id} замьючен на {minutes} мин: {reason}"


def ban_user(user_id: int, reason: str) -> str:
    return f"Пользователь {user_id} забанен: {reason}"
