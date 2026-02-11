"""Команды управления ПК (использовать только после подтверждения)."""


def shutdown_pc(delay_minutes: int = 0) -> str:
    return f"Команда выключения принята, задержка: {delay_minutes} минут"


def reboot_pc(delay_minutes: int = 0) -> str:
    return f"Команда перезагрузки принята, задержка: {delay_minutes} минут"
