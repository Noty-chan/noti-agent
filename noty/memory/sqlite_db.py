"""SQLite-менеджер с таблицами по спецификации."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List


class SQLiteDBManager:
    def __init__(self, db_path: str = "./noty/data/noty.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        conn = self._connect()
        cur = conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_seen TIMESTAMP,
                last_seen TIMESTAMP,
                message_count INTEGER DEFAULT 0,
                relationship_score INTEGER DEFAULT 0,
                preferred_tone TEXT,
                traits TEXT,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS chats (
                chat_id INTEGER PRIMARY KEY,
                chat_name TEXT,
                is_group BOOLEAN,
                noty_is_admin BOOLEAN,
                activity_level TEXT,
                last_interesting_topic TEXT,
                created_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP,
                platform TEXT DEFAULT 'unknown',
                chat_id INTEGER,
                user_id INTEGER,
                message_text TEXT,
                noty_responded BOOLEAN,
                response_text TEXT,
                mood_before TEXT,
                mood_after TEXT,
                tools_used TEXT
            );

            CREATE TABLE IF NOT EXISTS moderation (
                user_id INTEGER,
                chat_id INTEGER,
                action TEXT,
                reason TEXT,
                timestamp TIMESTAMP,
                expires_at TIMESTAMP,
                PRIMARY KEY (user_id, chat_id, action)
            );

            CREATE TABLE IF NOT EXISTS prompt_versions (
                version INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP,
                personality_layer TEXT,
                mood_layer TEXT,
                reason_for_change TEXT,
                signal_source TEXT,
                approved BOOLEAN DEFAULT FALSE
            );

            CREATE TABLE IF NOT EXISTS personality_change_proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP,
                author TEXT NOT NULL,
                diff_summary TEXT NOT NULL,
                risk TEXT NOT NULL,
                decision TEXT DEFAULT 'pending',
                reviewer TEXT
            );

            CREATE TABLE IF NOT EXISTS user_persona_profiles (
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                preferred_style TEXT DEFAULT 'balanced',
                sarcasm_tolerance REAL DEFAULT 0.5,
                taboo_topics TEXT DEFAULT '[]',
                motivators TEXT DEFAULT '[]',
                response_depth_preference TEXT DEFAULT 'medium',
                confidence REAL DEFAULT 0.0,
                source TEXT DEFAULT 'default',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, chat_id)
            );

            """
        )
        interaction_cols = {row[1] for row in cur.execute("PRAGMA table_info(interactions)").fetchall()}
        if "platform" not in interaction_cols:
            cur.execute("ALTER TABLE interactions ADD COLUMN platform TEXT DEFAULT 'unknown'")
        # Backfill policy: все legacy записи без platform маркируем как unknown.
        cur.execute("UPDATE interactions SET platform='unknown' WHERE platform IS NULL OR platform='' ")

        cols = {row[1] for row in cur.execute("PRAGMA table_info(prompt_versions)").fetchall()}
        if "signal_source" not in cols:
            cur.execute("ALTER TABLE prompt_versions ADD COLUMN signal_source TEXT DEFAULT ''")
        conn.commit()
        conn.close()

    def get_recent_messages(self, platform: str, chat_id: int, limit: int = 5) -> List[Dict[str, Any]]:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id, message_text as text, timestamp FROM interactions WHERE platform=? AND chat_id=? ORDER BY id DESC LIMIT ?",
            (platform, chat_id, limit),
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return list(reversed(rows))

    def get_messages_range(self, platform: str, chat_id: int, days_ago: int = 7, exclude_recent: int = 5) -> List[Dict[str, Any]]:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id, message_text as text, timestamp FROM interactions WHERE platform=? AND chat_id=? ORDER BY id DESC LIMIT 200",
            (platform, chat_id),
        )
        rows = [dict(r) for r in cur.fetchall()][exclude_recent:]
        conn.close()
        return list(reversed(rows))

    def get_important_messages(self, platform: str, chat_id: int, days_ago: int = 7) -> List[Dict[str, Any]]:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id, message_text as text, timestamp, 'question_or_mention' as type FROM interactions WHERE platform=? AND chat_id=? AND message_text LIKE '%?%' ORDER BY id DESC LIMIT 20",
            (platform, chat_id),
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows


    def create_personality_proposal(self, author: str, diff_summary: str, risk: str) -> int:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO personality_change_proposals (created_at, author, diff_summary, risk)
            VALUES (CURRENT_TIMESTAMP, ?, ?, ?)
            """,
            (author, diff_summary, risk),
        )
        proposal_id = int(cur.lastrowid)
        conn.commit()
        conn.close()
        return proposal_id

    def review_personality_proposal(self, proposal_id: int, decision: str, reviewer: str) -> None:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE personality_change_proposals
            SET decision = ?, reviewer = ?
            WHERE id = ?
            """,
            (decision, reviewer, proposal_id),
        )
        conn.commit()
        conn.close()

    def get_user_persona_profile(self, user_id: int, chat_id: int) -> Dict[str, Any] | None:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT preferred_style, sarcasm_tolerance, taboo_topics, motivators,
                   response_depth_preference, confidence, source
            FROM user_persona_profiles
            WHERE user_id=? AND chat_id=?
            """,
            (user_id, chat_id),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "preferred_style": row["preferred_style"],
            "sarcasm_tolerance": float(row["sarcasm_tolerance"] or 0.0),
            "taboo_topics": __import__("json").loads(row["taboo_topics"] or "[]"),
            "motivators": __import__("json").loads(row["motivators"] or "[]"),
            "response_depth_preference": row["response_depth_preference"],
            "confidence": float(row["confidence"] or 0.0),
            "source": row["source"] or "default",
        }

    def upsert_user_persona_profile(self, user_id: int, chat_id: int, profile: Dict[str, Any]) -> None:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO user_persona_profiles (
                user_id, chat_id, preferred_style, sarcasm_tolerance, taboo_topics,
                motivators, response_depth_preference, confidence, source, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, chat_id) DO UPDATE SET
                preferred_style=excluded.preferred_style,
                sarcasm_tolerance=excluded.sarcasm_tolerance,
                taboo_topics=excluded.taboo_topics,
                motivators=excluded.motivators,
                response_depth_preference=excluded.response_depth_preference,
                confidence=excluded.confidence,
                source=excluded.source,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                user_id,
                chat_id,
                profile.get("preferred_style", "balanced"),
                float(profile.get("sarcasm_tolerance", 0.5)),
                __import__("json").dumps(profile.get("taboo_topics", []), ensure_ascii=False),
                __import__("json").dumps(profile.get("motivators", []), ensure_ascii=False),
                profile.get("response_depth_preference", "medium"),
                float(profile.get("confidence", 0.0)),
                profile.get("source", "default"),
            ),
        )
        conn.commit()
        conn.close()
