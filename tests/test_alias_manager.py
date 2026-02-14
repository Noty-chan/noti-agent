from pathlib import Path

from noty.memory.alias_manager import UserAliasManager
from noty.memory.sqlite_db import SQLiteDBManager


def test_alias_extraction_and_persist(tmp_path: Path):
    db = SQLiteDBManager(str(tmp_path / "noty.db"))
    manager = UserAliasManager(db_manager=db)

    result = manager.extract_and_persist(chat_id=100, user_id=7, text="Можешь звать меня Лис")

    assert result.aliases
    alias = manager.get_preferred_alias(chat_id=100, user_id=7)
    assert alias == "лис"


def test_alias_requires_confirmation_prompt(tmp_path: Path):
    db = SQLiteDBManager(str(tmp_path / "noty.db"))
    manager = UserAliasManager(db_manager=db)

    result = manager.extract_alias_signals("Это Ваня, его кличка Вихрь", user_id=5)

    assert result.should_ask_confirmation is True
