"""Малый блокнот Ноти с жёсткими лимитами и jsonl-аудитом."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from noty.memory.sqlite_db import SQLiteDBManager


class NotiNotebookManager:
    def __init__(
        self,
        db_manager: SQLiteDBManager,
        max_entries: int = 25,
        max_total_chars: int = 4000,
        max_entry_chars: int = 280,
        logs_dir: str = "./noty/data/logs/notebook",
    ):
        self.db = db_manager
        self.max_entries = int(max_entries)
        self.max_total_chars = int(max_total_chars)
        self.max_entry_chars = int(max_entry_chars)
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def get_limits(self) -> Dict[str, int]:
        return {
            "max_entries": self.max_entries,
            "max_total_chars": self.max_total_chars,
            "max_entry_chars": self.max_entry_chars,
        }

    def list_notes(self, chat_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        conn = self.db._connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, note, created_at, updated_at
            FROM noti_notebook
            WHERE chat_id = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            (chat_id, max(limit, 1)),
        )
        rows = [dict(row) for row in cur.fetchall()]
        conn.close()
        return rows

    def add_note(self, chat_id: int, note: str) -> Dict[str, Any]:
        normalized = self._validate_note(note)
        ok, reason = self._can_fit_new(chat_id=chat_id, new_note=normalized)
        if not ok:
            return {"status": "limit_exceeded", "message": reason, "limits": self.get_limits()}

        conn = self.db._connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO noti_notebook (chat_id, note, created_at, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (chat_id, normalized),
        )
        note_id = int(cur.lastrowid)
        conn.commit()
        conn.close()
        payload = {"status": "success", "note_id": note_id, "note": normalized}
        self._log_change("notebook_add", chat_id=chat_id, payload=payload)
        return payload

    def update_note(self, chat_id: int, note_id: int, note: str) -> Dict[str, Any]:
        normalized = self._validate_note(note)
        conn = self.db._connect()
        cur = conn.cursor()
        cur.execute("SELECT id, note FROM noti_notebook WHERE id=? AND chat_id=?", (note_id, chat_id))
        row = cur.fetchone()
        if not row:
            conn.close()
            return {"status": "not_found", "message": "Заметка не найдена."}

        current_total = self._total_chars(chat_id)
        projected_total = current_total - len(row["note"]) + len(normalized)
        if projected_total > self.max_total_chars:
            conn.close()
            return {
                "status": "limit_exceeded",
                "message": f"Лимит блокнота превышен: {projected_total}/{self.max_total_chars} символов.",
                "limits": self.get_limits(),
            }

        cur.execute(
            "UPDATE noti_notebook SET note=?, updated_at=CURRENT_TIMESTAMP WHERE id=? AND chat_id=?",
            (normalized, note_id, chat_id),
        )
        conn.commit()
        conn.close()
        payload = {"status": "success", "note_id": note_id, "note": normalized}
        self._log_change("notebook_update", chat_id=chat_id, payload=payload)
        return payload

    def delete_note(self, chat_id: int, note_id: int) -> Dict[str, Any]:
        conn = self.db._connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM noti_notebook WHERE id=? AND chat_id=?", (note_id, chat_id))
        affected = cur.rowcount
        conn.commit()
        conn.close()
        if not affected:
            return {"status": "not_found", "message": "Заметка не найдена."}
        payload = {"status": "success", "note_id": note_id}
        self._log_change("notebook_delete", chat_id=chat_id, payload=payload)
        return payload

    def list_notes_tool(self, chat_id: int, limit: int = 20) -> Dict[str, Any]:
        notes = self.list_notes(chat_id=chat_id, limit=limit)
        return {"status": "success", "notes": notes, "limits": self.get_limits()}

    def _total_chars(self, chat_id: int) -> int:
        conn = self.db._connect()
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(SUM(LENGTH(note)), 0) AS total_chars FROM noti_notebook WHERE chat_id=?", (chat_id,))
        row = cur.fetchone()
        conn.close()
        return int(row["total_chars"] if row else 0)

    def _can_fit_new(self, chat_id: int, new_note: str) -> tuple[bool, str]:
        conn = self.db._connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS total FROM noti_notebook WHERE chat_id=?", (chat_id,))
        count_row = cur.fetchone()
        cur.execute("SELECT COALESCE(SUM(LENGTH(note)), 0) AS chars_total FROM noti_notebook WHERE chat_id=?", (chat_id,))
        chars_row = cur.fetchone()
        conn.close()

        total = int(count_row["total"] if count_row else 0)
        chars_total = int(chars_row["chars_total"] if chars_row else 0)
        if total >= self.max_entries:
            return False, f"Лимит записей достигнут: {total}/{self.max_entries}."
        projected = chars_total + len(new_note)
        if projected > self.max_total_chars:
            return False, f"Лимит символов превышен: {projected}/{self.max_total_chars}."
        return True, ""

    def _validate_note(self, note: str) -> str:
        normalized = (note or "").strip()
        if not normalized:
            raise ValueError("Заметка не может быть пустой.")
        if len(normalized) > self.max_entry_chars:
            raise ValueError(f"Заметка слишком длинная: {len(normalized)}/{self.max_entry_chars} символов.")
        return normalized

    def _log_change(self, action: str, chat_id: int, payload: Dict[str, Any]) -> None:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "chat_id": chat_id,
            "payload": payload,
        }
        day_file = self.logs_dir / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        with open(day_file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

