from pathlib import Path

from noty.core.context_manager import DynamicContextBuilder
from noty.memory.notebook import NotiNotebookManager
from noty.memory.sqlite_db import SQLiteDBManager
from noty.prompts.prompt_builder import ModularPromptBuilder


class _DummyEncoder:
    def encode(self, text: str):
        return [float(len(text) or 1)]


class _DummyEmbeddingFilter:
    def __init__(self):
        self.encoder = _DummyEncoder()


def test_notebook_limits_and_context_integration(tmp_path: Path):
    db = SQLiteDBManager(str(tmp_path / "noty.db"))
    notebook = NotiNotebookManager(db_manager=db, max_entries=2, max_total_chars=20, max_entry_chars=10, logs_dir=str(tmp_path / "logs"))

    first = notebook.add_note(chat_id=100, note="важно")
    second = notebook.add_note(chat_id=100, note="помнить")
    third = notebook.add_note(chat_id=100, note="коротко")

    assert first["status"] == "success"
    assert second["status"] == "success"
    assert third["status"] == "limit_exceeded"

    builder = DynamicContextBuilder(db_manager=db, embedding_filter=_DummyEmbeddingFilter())
    context = builder.build_context(platform="vk", chat_id=100, current_message="что там", user_id=1)

    assert context["sources"]["notebook"] >= 1
    assert context["metadata"]["notebook_limits"]["max_entries"] == 25
    assert any("[NOTE#" in message["content"] for message in context["messages"])


def test_prompt_contains_notebook_limits_layer(tmp_path: Path):
    builder = ModularPromptBuilder(str(tmp_path / "prompts"), config_path=str(tmp_path / "cfg.json"))
    context = {
        "messages": [],
        "summary": "",
        "metadata": {
            "notebook_limits": {
                "max_entries": 25,
                "max_total_chars": 4000,
                "max_entry_chars": 280,
            }
        },
    }
    prompt = builder.build_full_prompt(context=context)

    assert "БЛОКНОТ НОТИ (жёсткие лимиты)" in prompt
    assert "max_entries: 25" in prompt
