from __future__ import annotations

from pathlib import Path

from noty.core.context_manager import DynamicContextBuilder
from noty.memory.mem0_wrapper import Mem0Wrapper
from noty.memory.sqlite_db import SQLiteDBManager


class _DummyEncoder:
    def encode(self, text: str):
        return [float(len(text) or 1)]


class _DummyEmbeddingFilter:
    def __init__(self):
        self.encoder = _DummyEncoder()


class _FakeMem0Client:
    def __init__(self):
        self.items = []

    def add(self, text, user_id=None, metadata=None):
        self.items.append({"text": text, "user_id": user_id, "metadata": metadata or {}})

    def search(self, query, user_id=None, limit=5):
        rows = [x for x in self.items if user_id is None or x["user_id"] == user_id]
        return rows[:limit]


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


def test_dynamic_context_builder_isolates_by_platform_and_chat(tmp_path: Path):
    db = SQLiteDBManager(str(tmp_path / "ctx.db"))
    _insert_interaction(db, "vk", 100, "vk-message")
    _insert_interaction(db, "tg", 100, "tg-message")

    builder = DynamicContextBuilder(db_manager=db, embedding_filter=_DummyEmbeddingFilter())
    context = builder.build_context(platform="vk", chat_id=100, current_message="vk", user_id=1)

    contents = [m["content"] for m in context["messages"]]
    assert "vk-message" in contents
    assert "tg-message" not in contents


def test_mem0_recall_isolates_scope_metadata():
    fake = _FakeMem0Client()
    mem = Mem0Wrapper(memory_client=fake)
    mem.remember("vk data", user_id="u1", platform="vk", chat_id=100)
    mem.remember("tg data", user_id="u1", platform="tg", chat_id=100)

    recalls = mem.recall("data", user_id="u1", platform="vk", chat_id=100)

    assert len(recalls) == 1
    assert recalls[0]["text"] == "vk data"
