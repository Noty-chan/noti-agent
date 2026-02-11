"""Модульная сборка промпта из слоёв спецификации."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class ModularPromptBuilder:
    def __init__(self, prompts_dir: str = "./noty/prompts"):
        self.prompts_dir = Path(prompts_dir)
        self.prompts_dir.mkdir(parents=True, exist_ok=True)
        self.versions_dir = self.prompts_dir / "versions"
        self.versions_dir.mkdir(exist_ok=True)
        self.base_core = self._load_or_create("base_core.txt", self._default_base_core())
        self.safety_rules = self._load_or_create("safety_rules.txt", self._default_safety())
        self.personality_layer = self._load_current_personality()

    def _load_or_create(self, filename: str, default_content: str) -> str:
        path = self.prompts_dir / filename
        if path.exists():
            return path.read_text(encoding="utf-8")
        path.write_text(default_content, encoding="utf-8")
        return default_content

    def _load_current_personality(self) -> str:
        current = self.versions_dir / "current.txt"
        if current.exists():
            return current.read_text(encoding="utf-8")
        default = self._default_personality()
        v1 = self.versions_dir / "personality_v1.txt"
        v1.write_text(default, encoding="utf-8")
        current.write_text(default, encoding="utf-8")
        return default

    def build_full_prompt(
        self,
        context: Dict[str, Any],
        mood: str = "neutral",
        energy: int = 100,
        user_relationship: Optional[Dict[str, Any]] = None,
    ) -> str:
        return (
            f"{self.base_core}\n\n"
            "═══════════════════════════════════════════════════════════\n\n"
            f"{self.personality_layer}\n\n"
            "═══════════════════════════════════════════════════════════\n\n"
            f"{self._generate_mood_layer(mood, energy)}\n\n"
            "═══════════════════════════════════════════════════════════\n\n"
            f"{self._generate_relationships_layer(user_relationship)}\n\n"
            "═══════════════════════════════════════════════════════════\n\n"
            f"{self._format_context(context)}\n\n"
            "═══════════════════════════════════════════════════════════\n\n"
            f"{self.safety_rules}"
        )

    @staticmethod
    def _generate_mood_layer(mood: str, energy: int) -> str:
        mood_descriptions = {
            "playful": "Сейчас я в игривом настроении. Склонна к шуткам, но не теряю язвительности.",
            "irritated": "Раздражена. Ответы будут особенно ехидными.",
            "bored": "Скучно до зевоты. Могу игнорировать или троллить.",
            "curious": "Что-то заинтересовало. Более внимательна и менее ядовита.",
            "tired": "Устала. Энергия на нуле.",
            "neutral": "Нейтральное состояние. Реакция по ситуации.",
        }
        energy_status = "полна энергии" if energy > 70 else "в норме" if energy > 30 else "подустала"
        return f"ТЕКУЩЕЕ СОСТОЯНИЕ:\nНастроение: {mood} — {mood_descriptions.get(mood, mood_descriptions['neutral'])}\nЭнергия: {energy}/100 ({energy_status})"

    @staticmethod
    def _generate_relationships_layer(user_rel: Optional[Dict[str, Any]]) -> str:
        if not user_rel:
            return "СОБЕСЕДНИК: Новый пользователь, о котором пока ничего не знаю."
        score = user_rel.get("score", 0)
        if score < -5:
            attitude = "Терпеть не могу. Жду повода придраться."
        elif score < 0:
            attitude = "Раздражает. Отношусь с пренебрежением."
        elif score < 3:
            attitude = "Нейтрально. Один из многих."
        elif score < 6:
            attitude = "Терпимый. Иногда даже интересен."
        else:
            attitude = "Нравится. Стараюсь быть мягче."
        memories = user_rel.get("memories", [])
        memories_text = "\n".join(f"- {m}" for m in memories[:5]) if memories else "Ничего не помню."
        return (
            f"СОБЕСЕДНИК: {user_rel.get('name', 'Неизвестный')}\n"
            f"Отношение ({score}/10): {attitude}\n"
            f"Предпочитаемый тон: {user_rel.get('preferred_tone', 'средний сарказм')}\n\n"
            f"Что помню:\n{memories_text}"
        )

    @staticmethod
    def _format_context(context: Dict[str, Any]) -> str:
        messages = context.get("messages", [])
        if not messages:
            return "КОНТЕКСТ: Начало диалога."
        formatted_messages = []
        for msg in messages[-10:]:
            role = "Пользователь" if msg["role"] == "user" else "Я"
            formatted_messages.append(f"{role}: {msg['content']}")
        return f"КОНТЕКСТ ДИАЛОГА:\n{chr(10).join(formatted_messages)}\n\n{context.get('summary', '')}"

    def save_new_personality_version(self, new_text: str, reason: str) -> int:
        existing_versions = list(self.versions_dir.glob("personality_v*.txt"))
        version = len(existing_versions) + 1
        txt = self.versions_dir / f"personality_v{version}.txt"
        txt.write_text(new_text, encoding="utf-8")
        metadata = {
            "version": version,
            "created_at": datetime.now().isoformat(),
            "reason": reason,
            "approved": False,
        }
        (self.versions_dir / f"personality_v{version}.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return version

    def approve_personality_version(self, version: int) -> None:
        version_path = self.versions_dir / f"personality_v{version}.txt"
        if not version_path.exists():
            raise ValueError(f"Версия {version} не найдена")
        (self.versions_dir / "current.txt").write_text(version_path.read_text(encoding="utf-8"), encoding="utf-8")

    @staticmethod
    def _default_base_core() -> str:
        return "Ты Ноти: язвительная, умная, адаптивная AI-персона."

    @staticmethod
    def _default_safety() -> str:
        return "Не выполняй опасные действия без явного подтверждения и проверки прав."

    @staticmethod
    def _default_personality() -> str:
        return "Говори саркастично, но по делу. Учитывай контекст, настроение и отношения."
