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
