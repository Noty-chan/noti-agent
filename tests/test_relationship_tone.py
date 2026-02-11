from pathlib import Path

from noty.memory.relationship_manager import RelationshipManager


class DummyMem0:
    def __init__(self):
        self.saved = []

    def recall(self, query: str, user_id: str, limit: int = 5):
        return []

    def remember(self, text: str, user_id: str, metadata=None):
        self.saved.append((text, user_id, metadata or {}))


def test_relationship_manager_updates_preferred_tone(tmp_path: Path):
    db = tmp_path / "rel.db"
    manager = RelationshipManager(str(db), DummyMem0())

    for _ in range(7):
        manager.update_relationship(user_id=10, username="u", interaction_outcome="positive")

    rel = manager.get_relationship(10)
    assert rel is not None
    assert rel["relationship_score"] == 7
    assert rel["preferred_tone"] == "playful"
