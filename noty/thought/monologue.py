"""Внутренний монолог и логирование мыслей Ноти."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from noty.core.api_rotator import APIRotator


class ThoughtLogger:
    def __init__(self, logs_dir: str = "./noty/data/logs/thoughts"):
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def _get_today_file(self) -> Path:
        return self.logs_dir / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"

    def log_thought(self, thought_entry: Dict[str, Any]):
        if "timestamp" not in thought_entry:
            thought_entry["timestamp"] = datetime.now().isoformat()
        with open(self._get_today_file(), "a", encoding="utf-8") as file:
            file.write(json.dumps(thought_entry, ensure_ascii=False) + "\n")

    def read_today_thoughts(self) -> List[Dict[str, Any]]:
        file = self._get_today_file()
        if not file.exists():
            return []
        return [json.loads(line) for line in file.read_text(encoding="utf-8").splitlines() if line.strip()]

    def read_thoughts_range(self, days: int = 7) -> List[Dict[str, Any]]:
        thoughts: List[Dict[str, Any]] = []
        for i in range(days):
            date_str = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            file = self.logs_dir / f"{date_str}.jsonl"
            if file.exists():
                thoughts.extend(json.loads(line) for line in file.read_text(encoding="utf-8").splitlines() if line.strip())
        return thoughts


class InternalMonologue:
    def __init__(self, api_rotator: APIRotator, thought_logger: ThoughtLogger):
        self.api = api_rotator
        self.logger = thought_logger

    def generate_thoughts(self, context: Dict[str, Any], cheap_model: bool = True) -> Dict[str, Any]:
        prompt = (
            f"Ситуация:\n- Чат: {context.get('chat_name', 'Неизвестный')}\n"
            f"- Пользователь: {context.get('username', 'Неизвестный')} (отношение: {context.get('relationship_score', 0)}/10)\n"
            f"- Сообщение: \"{context.get('message', '')}\"\n"
            f"- Моё настроение: {context.get('mood', 'neutral')}\n"
            f"- Энергия: {context.get('energy', 100)}/100\n\n"
            "Подумай вслух (3-7 коротких мыслей) и выбери стратегию ответа."
        )
        model = "meta-llama/llama-3.1-8b-instruct" if cheap_model else "meta-llama/llama-3.1-70b-instruct"
        response = self.api.call(messages=[{"role": "user", "content": prompt}], model=model, temperature=0.8, max_tokens=300)
        thoughts = [line.strip().lstrip("0123456789.-) ") for line in response["content"].split("\n") if line.strip()]
        thought_entry = {
            "timestamp": datetime.now().isoformat(),
            "chat_id": context.get("chat_id"),
            "chat_name": context.get("chat_name"),
            "user_id": context.get("user_id"),
            "username": context.get("username"),
            "trigger": "message_received",
            "message": context.get("message"),
            "thoughts": thoughts,
            "mood_before": context.get("mood"),
            "energy_before": context.get("energy"),
        }
        self.logger.log_thought(thought_entry)
        return thought_entry
