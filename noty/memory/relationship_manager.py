"""Менеджер отношений Ноти с пользователями."""

from __future__ import annotations

import sqlite3
import json
from datetime import datetime
from typing import Any, Dict, Optional, Protocol


class MemoryLike(Protocol):
    def recall(self, query: str, user_id: str, limit: int = 5): ...

    def remember(self, text: str, user_id: str, metadata: Optional[Dict] = None): ...


class RelationshipManager:
    def __init__(self, db_path: str, mem0: MemoryLike):
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
                tone_success_stats TEXT DEFAULT '{}',
                tone_fail_stats TEXT DEFAULT '{}',
                recent_outcomes TEXT DEFAULT '',
                notes TEXT
            )
            """
        )
        existing_columns = {
            row[1] for row in cursor.execute("PRAGMA table_info(relationships)").fetchall()
        }
        if "tone_success_stats" not in existing_columns:
            cursor.execute("ALTER TABLE relationships ADD COLUMN tone_success_stats TEXT DEFAULT '{}' ")
        if "tone_fail_stats" not in existing_columns:
            cursor.execute("ALTER TABLE relationships ADD COLUMN tone_fail_stats TEXT DEFAULT '{}' ")
        if "recent_outcomes" not in existing_columns:
            cursor.execute("ALTER TABLE relationships ADD COLUMN recent_outcomes TEXT DEFAULT ''")
        conn.commit()
        conn.close()

    @staticmethod
    def _load_stats(raw_stats: Optional[str]) -> Dict[str, int]:
        if not raw_stats:
            return {}
        try:
            parsed = json.loads(raw_stats)
            return {str(k): int(v) for k, v in parsed.items()}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _dump_stats(stats: Dict[str, int]) -> str:
        return json.dumps(stats, ensure_ascii=False)

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
        rel["tone_success_stats"] = self._load_stats(rel.get("tone_success_stats"))
        rel["tone_fail_stats"] = self._load_stats(rel.get("tone_fail_stats"))
        rel["recent_outcomes"] = [x for x in (rel.get("recent_outcomes") or "").split(",") if x]
        memories = self.mem0.recall("что я знаю об этом пользователе", user_id=f"user_{user_id}", limit=5)
        rel["memories"] = [m["text"] for m in memories]
        return rel

    def get_relationship_trend(self, user_id: int) -> Dict[str, Any]:
        relationship = self.get_relationship(user_id)
        if not relationship:
            return {
                "score": 0,
                "positive_ratio": 0.5,
                "negative_streak": 0,
                "recent_outcomes": [],
            }
        positive = relationship.get("positive_interactions", 0)
        negative = relationship.get("negative_interactions", 0)
        total = positive + negative
        positive_ratio = (positive / total) if total else 0.5
        recent_outcomes = relationship.get("recent_outcomes", [])
        negative_streak = 0
        for outcome in reversed(recent_outcomes):
            if outcome == "negative":
                negative_streak += 1
            else:
                break
        return {
            "score": relationship.get("relationship_score", 0),
            "positive_ratio": positive_ratio,
            "negative_streak": negative_streak,
            "recent_outcomes": recent_outcomes,
            "tone_success_stats": relationship.get("tone_success_stats", {}),
            "tone_fail_stats": relationship.get("tone_fail_stats", {}),
        }

    @staticmethod
    def _derive_preferred_tone(score: int, positive_ratio: float) -> str:
        if score >= 6:
            return "playful"
        if score <= -6:
            return "harsh"
        if positive_ratio >= 0.7 and score > 2:
            return "mild_sarcasm"
        if positive_ratio <= 0.3 and score < -2:
            return "dry"
        return "medium_sarcasm"

    def update_relationship(
        self,
        user_id: int,
        username: str,
        interaction_outcome: str,
        notes: Optional[str] = None,
        tone_used: Optional[str] = None,
    ):
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
            tone_success_stats: Dict[str, int] = {}
            tone_fail_stats: Dict[str, int] = {}
            recent_outcomes: list[str] = []
        else:
            current_score = row[0]
            cursor.execute(
                "SELECT tone_success_stats, tone_fail_stats, recent_outcomes FROM relationships WHERE user_id = ?",
                (user_id,),
            )
            tone_row = cursor.fetchone()
            tone_success_stats = self._load_stats(tone_row[0]) if tone_row else {}
            tone_fail_stats = self._load_stats(tone_row[1]) if tone_row else {}
            recent_outcomes = [x for x in (tone_row[2] or "").split(",") if x] if tone_row else []

        score_change = {"positive": 1, "negative": -1, "neutral": 0}.get(interaction_outcome, 0)
        new_score = max(-10, min(10, current_score + score_change))

        positive_delta = 1 if interaction_outcome == "positive" else 0
        negative_delta = 1 if interaction_outcome == "negative" else 0
        if tone_used:
            if interaction_outcome == "positive":
                tone_success_stats[tone_used] = tone_success_stats.get(tone_used, 0) + 1
            elif interaction_outcome == "negative":
                tone_fail_stats[tone_used] = tone_fail_stats.get(tone_used, 0) + 1
        if interaction_outcome in {"positive", "negative"}:
            recent_outcomes.append(interaction_outcome)
            recent_outcomes = recent_outcomes[-10:]

        cursor.execute(
            """
            UPDATE relationships
            SET relationship_score = ?,
                last_seen = ?,
                message_count = message_count + 1,
                positive_interactions = positive_interactions + ?,
                negative_interactions = negative_interactions + ?,
                tone_success_stats = ?,
                tone_fail_stats = ?,
                recent_outcomes = ?,
                notes = ?
            WHERE user_id = ?
            """,
            (
                new_score,
                datetime.now(),
                positive_delta,
                negative_delta,
                self._dump_stats(tone_success_stats),
                self._dump_stats(tone_fail_stats),
                ",".join(recent_outcomes),
                notes or "",
                user_id,
            ),
        )

        cursor.execute(
            """
            SELECT positive_interactions, negative_interactions
            FROM relationships
            WHERE user_id = ?
            """,
            (user_id,),
        )
        totals_row = cursor.fetchone()
        positive_total = totals_row[0] if totals_row else 0
        negative_total = totals_row[1] if totals_row else 0
        total_feedback = positive_total + negative_total
        positive_ratio = (positive_total / total_feedback) if total_feedback else 0.5
        preferred_tone = tone_used or self._derive_preferred_tone(new_score, positive_ratio)
        cursor.execute(
            "UPDATE relationships SET preferred_tone = ? WHERE user_id = ?",
            (preferred_tone, user_id),
        )
        conn.commit()
        conn.close()

        if notes:
            self.mem0.remember(
                notes,
                user_id=f"user_{user_id}",
                metadata={
                    "type": "relationship_update",
                    "outcome": interaction_outcome,
                    "score": new_score,
                    "preferred_tone": preferred_tone,
                },
            )
