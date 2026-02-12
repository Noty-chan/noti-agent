from pathlib import Path

from noty.core.context_manager import DynamicContextBuilder
from noty.memory.sqlite_db import SQLiteDBManager


class _DummyEncoder:
    def encode(self, text: str):
        return [float(len(text) or 1)]


class _DummyEmbeddingFilter:
    def __init__(self):
        self.encoder = _DummyEncoder()


def _insert_interaction(db: SQLiteDBManager, platform: str, chat_id: int, text: str, user_id: int = 1):
    conn = db._connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO interactions (timestamp, platform, chat_id, user_id, message_text, noty_responded, response_text, mood_before, mood_after, tools_used)
        VALUES (datetime('now'), ?, ?, ?, ?, 0, '', 'neutral', 'neutral', '')
        """,
        (platform, chat_id, user_id, text),
    )
    conn.commit()
    conn.close()


def test_context_builder_marks_chat_atmosphere(tmp_path: Path):
    db = SQLiteDBManager(str(tmp_path / "ctx.db"))
    _insert_interaction(db, "vk", 100, "ты меня бесишь")
    _insert_interaction(db, "vk", 100, "это тупо")

    builder = DynamicContextBuilder(db_manager=db, embedding_filter=_DummyEmbeddingFilter())
    context = builder.build_context(platform="vk", chat_id=100, current_message="ок", user_id=1)

    assert context["metadata"]["chat_atmosphere"] == "toxic"
    assert "Атмосфера чата: toxic" in context["summary"]
