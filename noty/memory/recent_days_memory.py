"""Rolling memory последних дней с затуханием важности и maintenance."""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List


class RecentDaysMemory:
    """Слой памяти последних N дней поверх interactions.

    Хранит короткие факты в SQLite с затухающим весом, поддерживает maintenance и
    журналирует изменения в jsonl.
    """

    def __init__(
        self,
        db_manager: Any,
        *,
        days_window: int = 5,
        decay_lambda: float = 0.45,
        maintenance_interval_minutes: int = 30,
        max_items_per_chat: int = 200,
        logs_dir: str = "./noty/data/logs/rolling_memory",
    ):
        self.db = db_manager
        self.days_window = max(1, int(days_window))
        self.decay_lambda = max(0.01, float(decay_lambda))
        self.maintenance_interval = timedelta(minutes=max(5, int(maintenance_interval_minutes)))
        self.max_items_per_chat = max(50, int(max_items_per_chat))
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._last_maintenance_at: datetime | None = None
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        conn = self.db._connect()
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS recent_days_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                chat_id INTEGER NOT NULL,
                user_id INTEGER,
                memory_text TEXT NOT NULL,
                base_importance REAL DEFAULT 1.0,
                cached_weight REAL DEFAULT 1.0,
                source TEXT DEFAULT 'message',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_recent_days_scope_time "
            "ON recent_days_memory(platform, chat_id, created_at DESC)"
        )
        conn.commit()
        conn.close()

    @staticmethod
    def _as_dt(value: str | datetime | None) -> datetime:
        if value is None:
            return datetime.now()
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return datetime.now()

    def _decay_weight(self, base_importance: float, created_at: datetime, *, now: datetime | None = None) -> float:
        now_ts = now or datetime.now()
        age_days = max(0.0, (now_ts - created_at).total_seconds() / 86400.0)
        return float(base_importance) * math.exp(-self.decay_lambda * age_days)

    def _append_log(self, payload: Dict[str, Any]) -> None:
        day_file = self.logs_dir / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        with open(day_file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def remember_message(
        self,
        *,
        platform: str,
        chat_id: int,
        user_id: int,
        text: str,
        timestamp: str | datetime | None = None,
    ) -> None:
        cleaned_text = (text or "").strip()
        if not cleaned_text:
            return

        bonus = 0.0
        if "?" in cleaned_text:
            bonus += 0.35
        if len(cleaned_text) > 120:
            bonus += 0.15
        base_importance = min(2.5, 1.0 + bonus)
        created_at = self._as_dt(timestamp)
        weight = self._decay_weight(base_importance, created_at)

        conn = self.db._connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO recent_days_memory (
                platform, chat_id, user_id, memory_text, base_importance,
                cached_weight, source, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'message', ?, CURRENT_TIMESTAMP)
            """,
            (platform, chat_id, user_id, cleaned_text, base_importance, weight, created_at.isoformat()),
        )
        conn.commit()
        conn.close()

        self._append_log(
            {
                "timestamp": datetime.now().isoformat(),
                "event": "remember",
                "platform": platform,
                "chat_id": chat_id,
                "user_id": user_id,
                "base_importance": round(base_importance, 4),
                "cached_weight": round(weight, 4),
                "text": cleaned_text,
            }
        )

    def get_context_facts(
        self,
        *,
        platform: str,
        chat_id: int,
        limit: int = 4,
        min_weight: float = 0.2,
    ) -> List[Dict[str, Any]]:
        threshold_ts = (datetime.now() - timedelta(days=self.days_window)).isoformat()
        conn = self.db._connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, memory_text, created_at, base_importance, cached_weight
            FROM recent_days_memory
            WHERE platform=? AND chat_id=? AND created_at >= ?
            ORDER BY created_at DESC
            LIMIT 300
            """,
            (platform, chat_id, threshold_ts),
        )
        rows = [dict(row) for row in cur.fetchall()]
        conn.close()

        now_ts = datetime.now()
        weighted: List[Dict[str, Any]] = []
        for row in rows:
            created_at = self._as_dt(row.get("created_at"))
            decayed = self._decay_weight(float(row.get("base_importance", 1.0)), created_at, now=now_ts)
            if decayed < min_weight:
                continue
            weighted.append(
                {
                    "id": row["id"],
                    "text": row["memory_text"],
                    "created_at": created_at.isoformat(),
                    "weight": decayed,
                }
            )

        weighted.sort(key=lambda item: item["weight"], reverse=True)
        return weighted[: max(1, int(limit))]

    def run_maintenance_if_due(self) -> bool:
        now_ts = datetime.now()
        if self._last_maintenance_at and now_ts - self._last_maintenance_at < self.maintenance_interval:
            return False
        self._run_maintenance(now_ts)
        self._last_maintenance_at = now_ts
        return True

    def _run_maintenance(self, now_ts: datetime) -> None:
        retention_ts = (now_ts - timedelta(days=self.days_window * 2)).isoformat()
        conn = self.db._connect()
        cur = conn.cursor()

        cur.execute("DELETE FROM recent_days_memory WHERE created_at < ?", (retention_ts,))
        deleted = cur.rowcount

        cur.execute(
            """
            SELECT platform, chat_id, memory_text, MAX(created_at) as newest,
                   AVG(base_importance) as avg_importance, COUNT(*) as cnt
            FROM recent_days_memory
            GROUP BY platform, chat_id, memory_text
            HAVING cnt > 1
            """
        )
        duplicates = [dict(row) for row in cur.fetchall()]
        merged_total = 0
        for dup in duplicates:
            cur.execute(
                """
                DELETE FROM recent_days_memory
                WHERE platform=? AND chat_id=? AND memory_text=?
                """,
                (dup["platform"], dup["chat_id"], dup["memory_text"]),
            )
            merged_total += int(dup["cnt"])
            created_at = self._as_dt(dup["newest"])
            importance = float(dup["avg_importance"] or 1.0)
            weight = self._decay_weight(importance, created_at, now=now_ts)
            cur.execute(
                """
                INSERT INTO recent_days_memory (
                    platform, chat_id, user_id, memory_text, base_importance,
                    cached_weight, source, created_at, updated_at
                ) VALUES (?, ?, NULL, ?, ?, ?, 'maintenance_merge', ?, CURRENT_TIMESTAMP)
                """,
                (dup["platform"], dup["chat_id"], dup["memory_text"], importance, weight, created_at.isoformat()),
            )

        cur.execute("SELECT id, base_importance, created_at FROM recent_days_memory")
        for row in cur.fetchall():
            item = dict(row)
            created_at = self._as_dt(item.get("created_at"))
            weight = self._decay_weight(float(item.get("base_importance", 1.0)), created_at, now=now_ts)
            cur.execute(
                "UPDATE recent_days_memory SET cached_weight=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (weight, item["id"]),
            )

        cur.execute(
            """
            DELETE FROM recent_days_memory
            WHERE id IN (
                SELECT id FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (PARTITION BY platform, chat_id ORDER BY cached_weight DESC, created_at DESC) as rn
                    FROM recent_days_memory
                ) ranked
                WHERE rn > ?
            )
            """,
            (self.max_items_per_chat,),
        )
        trimmed = cur.rowcount

        conn.commit()
        conn.close()

        self._append_log(
            {
                "timestamp": now_ts.isoformat(),
                "event": "maintenance",
                "deleted_old": int(deleted),
                "merged_items": int(merged_total),
                "trimmed_overflow": int(trimmed),
                "days_window": self.days_window,
                "decay_lambda": self.decay_lambda,
            }
        )
