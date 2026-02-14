from pathlib import Path

from noty.memory.alias_manager import UserAliasManager
from noty.memory.sqlite_db import SQLiteDBManager


def test_alias_extraction_and_persist(tmp_path: Path):
    db = SQLiteDBManager(str(tmp_path / "noty.db"))
    manager = UserAliasManager(db_manager=db)

    result = manager.extract_and_persist(chat_id=100, user_id=7, text="Можешь звать меня Лис")

    assert result.aliases
    alias = manager.get_preferred_alias(chat_id=100, user_id=7)
    assert alias == "Лис"


def test_alias_requires_confirmation_prompt(tmp_path: Path):
    db = SQLiteDBManager(str(tmp_path / "noty.db"))
    manager = UserAliasManager(db_manager=db)

    result = manager.extract_alias_signals("Это Ваня, его кличка Вихрь", user_id=5)

    assert result.should_ask_confirmation is True


def test_alias_relation_signals_persist(tmp_path: Path):
    db = SQLiteDBManager(str(tmp_path / "noty.db"))
    manager = UserAliasManager(db_manager=db)

    result = manager.extract_and_persist(chat_id=555, user_id=11, text="Это Ваня, его кличка Вихрь")

    assert result.relation_signals
    links = manager.list_relation_signals(chat_id=555)
    assert links
    assert links[0]["target_display_name"] == "Ваня"
    assert links[0]["alias"] == "Вихрь"


def test_alias_rejects_dominance_titles(tmp_path: Path):
    db = SQLiteDBManager(str(tmp_path / "noty.db"))
    manager = UserAliasManager(db_manager=db)

    result = manager.extract_and_persist(chat_id=777, user_id=13, text="Зови меня Господин")

    assert result.aliases == []
    assert result.rejected_aliases
    assert result.rejected_aliases[0]["normalized_alias"] == "господин"
    assert manager.get_preferred_alias(chat_id=777, user_id=13) is None
