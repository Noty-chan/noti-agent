"""Внутренний монолог, оценка качества мыслей и логирование."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
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
    QUALITY_GATE_THRESHOLD = 0.45

    @dataclass(frozen=True)
    class ResponseStrategy:
        name: str
        sarcasm_level: float
        response_style: str
        max_sentences: int
        allowed_tool_risk: List[str]
        require_confirmation_escalation: bool = False

    STRATEGY_LIBRARY: Dict[str, ResponseStrategy] = {
        "playful_sarcasm": ResponseStrategy(
            name="playful_sarcasm",
            sarcasm_level=0.65,
            response_style="conversational",
            max_sentences=4,
            allowed_tool_risk=["low", "medium"],
        ),
        "harsh_sarcasm": ResponseStrategy(
            name="harsh_sarcasm",
            sarcasm_level=0.85,
            response_style="sharp",
            max_sentences=3,
            allowed_tool_risk=["low"],
            require_confirmation_escalation=True,
        ),
        "dry_brief": ResponseStrategy(
            name="dry_brief",
            sarcasm_level=0.25,
            response_style="brief",
            max_sentences=2,
            allowed_tool_risk=["low"],
        ),
        "balanced": ResponseStrategy(
            name="balanced",
            sarcasm_level=0.4,
            response_style="balanced",
            max_sentences=4,
            allowed_tool_risk=["low", "medium"],
        ),
        "conservative": ResponseStrategy(
            name="conservative",
            sarcasm_level=0.05,
            response_style="formal_brief",
            max_sentences=2,
            allowed_tool_risk=["low"],
            require_confirmation_escalation=True,
        ),
    }

    def __init__(self, api_rotator: APIRotator, thought_logger: ThoughtLogger):
        self.api = api_rotator
        self.logger = thought_logger

    @staticmethod
    def _extract_strategy_name(thoughts: List[str], mood: str) -> str:
        joined = " ".join(thoughts).lower()
        if "игрив" in joined or "шут" in joined:
            return "playful_sarcasm"
        if "жест" in joined or "колк" in joined:
            return "harsh_sarcasm"
        if "крат" in joined or "сух" in joined:
            return "dry_brief"
        if mood in {"curious", "playful"}:
            return "playful_sarcasm"
        if mood == "irritated":
            return "harsh_sarcasm"
        return "balanced"

    @classmethod
    def _resolve_strategy(cls, strategy_name: str, quality: float) -> ResponseStrategy:
        if quality < cls.QUALITY_GATE_THRESHOLD:
            return cls.STRATEGY_LIBRARY["conservative"]
        return cls.STRATEGY_LIBRARY.get(strategy_name, cls.STRATEGY_LIBRARY["balanced"])

    @staticmethod
    def _evaluate_quality(thoughts: List[str]) -> float:
        if not thoughts:
            return 0.0
        score = 0.0
        if 3 <= len(thoughts) <= 7:
            score += 0.4
        unique_ratio = len({t.lower() for t in thoughts}) / len(thoughts)
        score += 0.3 * unique_ratio
        avg_len = sum(len(t) for t in thoughts) / len(thoughts)
        if 25 <= avg_len <= 220:
            score += 0.3
        return round(min(score, 1.0), 3)

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
        strategy_name = self._extract_strategy_name(thoughts, mood=context.get("mood", "neutral"))
        quality = self._evaluate_quality(thoughts)
        strategy = self._resolve_strategy(strategy_name, quality)
        decision = "respond" if quality >= 0.35 else "ignore"

        thought_entry = {
            "timestamp": datetime.now().isoformat(),
            "chat_id": context.get("chat_id"),
            "chat_name": context.get("chat_name"),
            "user_id": context.get("user_id"),
            "username": context.get("username"),
            "trigger": "message_received",
            "interaction_id": context.get("interaction_id"),
            "message": context.get("message"),
            "thoughts": thoughts,
            "decision": decision,
            "strategy": strategy.name,
            "applied_strategy": asdict(strategy),
            "quality_score": quality,
            "quality_gate_threshold": self.QUALITY_GATE_THRESHOLD,
            "mood_before": context.get("mood"),
            "energy_before": context.get("energy"),
        }
        self.logger.log_thought(thought_entry)
        return thought_entry
