"""Менеджер отношений Ноти с пользователями."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Dict, Optional

from .mem0_wrapper import Mem0Wrapper


class RelationshipManager:
    def __init__(self, db_path: str, mem0: Mem0Wrapper):
        self.db_path = db_path
        self.mem0 = mem0
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS relationships (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                relationship_score INTEGER DEFAULT 0,
                preferred_tone TEXT DEFAULT 'medium_sarcasm',
                first_seen TIMESTAMP,
                last_seen TIMESTAMP,
                message_count INTEGER DEFAULT 0,
                positive_interactions INTEGER DEFAULT 0,
                negative_interactions INTEGER DEFAULT 0,
                notes TEXT
            )
            """
        )
        conn.commit()
        conn.close()

    def get_relationship(self, user_id: int) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM relationships WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        rel = dict(row)
        memories = self.mem0.recall("что я знаю об этом пользователе", user_id=f"user_{user_id}", limit=5)
        rel["memories"] = [m["text"] for m in memories]
        return rel

    def update_relationship(self, user_id: int, username: str, interaction_outcome: str, notes: Optional[str] = None):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT relationship_score FROM relationships WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()

        if row is None:
            cursor.execute(
                """
                INSERT INTO relationships (user_id, username, first_seen, last_seen, message_count)
                VALUES (?, ?, ?, ?, 1)
                """,
                (user_id, username, datetime.now(), datetime.now()),
            )
            current_score = 0
        else:
            current_score = row[0]

        score_change = {"positive": 1, "negative": -1, "neutral": 0}.get(interaction_outcome, 0)
        new_score = max(-10, min(10, current_score + score_change))

        cursor.execute(
            """
            UPDATE relationships
            SET relationship_score = ?,
                last_seen = ?,
                message_count = message_count + 1,
                positive_interactions = positive_interactions + ?,
                negative_interactions = negative_interactions + ?,
                notes = ?
            WHERE user_id = ?
            """,
            (
                new_score,
                datetime.now(),
                1 if interaction_outcome == "positive" else 0,
                1 if interaction_outcome == "negative" else 0,
                notes or "",
                user_id,
            ),
        )
        conn.commit()
        conn.close()

        if notes:
            self.mem0.remember(
                notes,
                user_id=f"user_{user_id}",
                metadata={"type": "relationship_update", "outcome": interaction_outcome, "score": new_score},
            )
