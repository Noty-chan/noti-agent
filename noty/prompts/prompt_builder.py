"""Модульная сборка промпта из слоёв спецификации."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .governance import ApprovalDecision, PersonalityProposal, RollbackEvent


class ModularPromptBuilder:
    def __init__(self, prompts_dir: str = "./noty/prompts", config_path: str = "./noty/config/persona_prompt_config.json"):
        self.prompts_dir = Path(prompts_dir)
        self.prompts_dir.mkdir(parents=True, exist_ok=True)
        self.versions_dir = self.prompts_dir / "versions"
        self.versions_dir.mkdir(exist_ok=True)
        self.config_path = Path(config_path)
        self.config = self._load_prompt_config()
        self.base_core = self._load_or_create("base_core.txt", self.config.get("base_core", self._default_base_core()))
        self.safety_rules = self._load_or_create("safety_rules.txt", self.config.get("safety_rules", self._default_safety()))
        self.personality_layer, self.current_personality_version = self._load_current_personality_with_version()

    def _load_prompt_config(self) -> Dict[str, Any]:
        default = {
            "prompt_markers": {"separator": "═══════════════════════════════════════════════════════════"},
            "base_core": self._default_base_core(),
            "safety_rules": self._default_safety(),
            "default_personality": self._default_personality(),
            "persona_adaptation_policy": {"version": 1, "reason": "initial", "policy_text": "Используй адаптивный стиль по профилю пользователя."},
            "conservative_fallback": {"preferred_tone": "neutral", "sarcasm_level": 0.1, "response_rate_bias": -0.05},
        }
        if self.config_path.exists():
            loaded = json.loads(self.config_path.read_text(encoding="utf-8"))
            merged = dict(default)
            merged.update(loaded)
            merged["prompt_markers"] = {**default["prompt_markers"], **(loaded.get("prompt_markers") or {})}
            return merged
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
        return default

    def _load_or_create(self, filename: str, default_content: str) -> str:
        path = self.prompts_dir / filename
        if path.exists():
            return path.read_text(encoding="utf-8")
        path.write_text(default_content, encoding="utf-8")
        return default_content

    def _load_current_personality_with_version(self) -> tuple[str, int]:
        current = self.versions_dir / "current.txt"
        if current.exists():
            current_text = current.read_text(encoding="utf-8")
            for path in self.versions_dir.glob("personality_v*.txt"):
                if path.read_text(encoding="utf-8") == current_text:
                    try:
                        return current_text, int(path.stem.replace("personality_v", ""))
                    except ValueError:
                        continue
            return current_text, 1
        default = self.config.get("default_personality", self._default_personality())
        v1 = self.versions_dir / "personality_v1.txt"
        v1.write_text(default, encoding="utf-8")
        current.write_text(default, encoding="utf-8")
        return default, 1

    def _build_personality_layer(self, runtime_modifiers: Optional[Dict[str, Any]] = None) -> str:
        modifiers = runtime_modifiers or {}
        preferred_tone = modifiers.get("preferred_tone", "medium_sarcasm")
        sarcasm_level = float(modifiers.get("sarcasm_level", 0.5))
        response_rate_bias = float(modifiers.get("response_rate_bias", 0.0))
        return (
            f"{self.personality_layer}\n\n"
            "RUNTIME PERSONALITY MODIFIERS:\n"
            f"- personality_version: v{self.current_personality_version}\n"
            f"- preferred_tone: {preferred_tone}\n"
            f"- sarcasm_level: {sarcasm_level:.2f} (0..1)\n"
            f"- response_rate_bias: {response_rate_bias:+.2f}"
        )

    def _build_persona_adaptation_layer(self, persona_profile: Optional[Dict[str, Any]] = None) -> str:
        policy = self.config.get("persona_adaptation_policy", {})
        return (
            "PERSONA ADAPTATION POLICY:\n"
            f"- version: {policy.get('version', 1)}\n"
            f"- reason_for_change: {policy.get('reason', 'initial')}\n"
            f"- policy: {policy.get('policy_text', '')}\n"
            f"- active_persona_profile: {json.dumps(persona_profile or {}, ensure_ascii=False)}"
        )

    def build_full_prompt(
        self,
        context: Dict[str, Any],
        mood: str = "neutral",
        energy: int = 100,
        user_relationship: Optional[Dict[str, Any]] = None,
        runtime_modifiers: Optional[Dict[str, Any]] = None,
        persona_profile: Optional[Dict[str, Any]] = None,
    ) -> str:
        personality_layer = self._build_personality_layer(runtime_modifiers)
        sep = self.config.get("prompt_markers", {}).get("separator", "═══════════════════════════════════════════════════════════")
        return (
            f"{self.base_core}\n\n"
            f"{sep}\n\n"
            f"{personality_layer}\n\n"
            f"{sep}\n\n"
            f"{self._build_persona_adaptation_layer(persona_profile)}\n\n"
            f"{sep}\n\n"
            f"{self._generate_mood_layer(mood, energy)}\n\n"
            f"{sep}\n\n"
            f"{self._generate_relationships_layer(user_relationship)}\n\n"
            f"{sep}\n\n"
            f"{self._format_context(context)}\n\n"
            f"{sep}\n\n"
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
        atmosphere = context.get("metadata", {}).get("chat_atmosphere", "unknown")
        global_memory = context.get("global_memory", "")
        persona_slice = context.get("persona_slice") or context.get("metadata", {}).get("persona_slice") or {}
        for msg in messages[-10:]:
            role = "Пользователь" if msg["role"] == "user" else "Я"
            formatted_messages.append(f"{role}: {msg['content']}")
        global_memory_block = f"\n\nГЛОБАЛЬНАЯ ПАМЯТЬ НОТИ:\n{global_memory}" if global_memory else ""
        persona_block = f"\n\nPERSONA-СРЕЗ ЧАТА:\n{json.dumps(persona_slice, ensure_ascii=False)}" if persona_slice else ""
        return (
            f"КОНТЕКСТ ДИАЛОГА (атмосфера: {atmosphere}):\n{chr(10).join(formatted_messages)}\n\n{context.get('summary', '')}"
            f"{persona_block}{global_memory_block}"
        )

    @staticmethod
    def _is_kpi_degraded(baseline: Dict[str, float], candidate: Dict[str, float], threshold: float) -> bool:
        for metric, before in baseline.items():
            if before <= 0:
                continue
            after = candidate.get(metric, before)
            if after < before * (1 - threshold):
                return True
        return False

    def dry_run_preview(self, proposal: PersonalityProposal, context: Dict[str, Any], mood: str = "neutral", energy: int = 100) -> Dict[str, Any]:
        preview_personality = (
            f"{proposal.new_personality_text}\n\n"
            "RUNTIME PERSONALITY MODIFIERS:\n"
            f"- personality_version: dry-run:{proposal.proposal_id}\n"
            "- preferred_tone: medium_sarcasm\n"
            "- sarcasm_level: 0.50 (0..1)\n"
            "- response_rate_bias: +0.00"
        )
        sep = self.config.get("prompt_markers", {}).get("separator", "═══════════════════════════════════════════════════════════")
        prompt = (
            f"{self.base_core}\n\n"
            f"{sep}\n\n"
            f"{preview_personality}\n\n"
            f"{sep}\n\n"
            f"{self._build_persona_adaptation_layer({})}\n\n"
            f"{sep}\n\n"
            f"{self._generate_mood_layer(mood, energy)}\n\n"
            f"{sep}\n\n"
            f"{self._generate_relationships_layer(None)}\n\n"
            f"{sep}\n\n"
            f"{self._format_context(context)}\n\n"
            f"{sep}\n\n"
            f"{self.safety_rules}"
        )
        return {
            "proposal_id": proposal.proposal_id,
            "preview_prompt": prompt,
            "status": "dry_run",
        }

    def approve_with_kpi_guardrails(
        self,
        proposal: PersonalityProposal,
        decision: ApprovalDecision,
        baseline_kpi: Dict[str, float],
        candidate_kpi: Dict[str, float],
        degradation_threshold: float = 0.05,
    ) -> Dict[str, Any]:
        if decision.decision.lower() != "approve":
            proposal.status = "rejected"
            return {"status": "rejected", "decision": decision.to_dict(), "proposal": proposal.to_dict()}

        previous_version = self.current_personality_version
        new_version = self.save_new_personality_version(proposal.new_personality_text, decision.reason)
        self.approve_personality_version(new_version)
        proposal.status = "approved"

        if self._is_kpi_degraded(baseline_kpi, candidate_kpi, degradation_threshold):
            rollback_to = self.rollback_personality_version(previous_version)
            rollback_event = RollbackEvent(
                proposal_id=proposal.proposal_id,
                from_version=new_version,
                to_version=rollback_to,
                trigger="kpi_degradation",
                kpi_before=baseline_kpi,
                kpi_after=candidate_kpi,
            )
            proposal.status = "rolled_back"
            return {
                "status": "rolled_back",
                "new_version": new_version,
                "current_version": self.current_personality_version,
                "rollback_event": rollback_event.to_dict(),
                "proposal": proposal.to_dict(),
                "decision": decision.to_dict(),
            }

        return {
            "status": "approved",
            "new_version": new_version,
            "current_version": self.current_personality_version,
            "proposal": proposal.to_dict(),
            "decision": decision.to_dict(),
        }

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
        self.personality_layer, self.current_personality_version = self._load_current_personality_with_version()

    def list_personality_versions(self) -> list[int]:
        versions = []
        for path in self.versions_dir.glob("personality_v*.txt"):
            try:
                versions.append(int(path.stem.replace("personality_v", "")))
            except ValueError:
                continue
        return sorted(versions)

    def rollback_personality_version(self, target_version: int | None = None) -> int:
        versions = self.list_personality_versions()
        if not versions:
            raise ValueError("Нет доступных версий personality для отката")

        if target_version is None:
            if len(versions) < 2:
                raise ValueError("Недостаточно версий для отката")
            target_version = versions[-2]
        elif target_version not in versions:
            raise ValueError(f"Версия {target_version} не найдена")

        self.approve_personality_version(target_version)
        self.personality_layer, self.current_personality_version = self._load_current_personality_with_version()
        return target_version

    @staticmethod
    def _default_base_core() -> str:
        return "Ты Ноти: язвительная, умная, адаптивная AI-персона."

    @staticmethod
    def _default_safety() -> str:
        return "Не выполняй опасные действия без явного подтверждения и проверки прав."

    @staticmethod
    def _default_personality() -> str:
        return "Говори саркастично, но по делу. Учитывай контекст, настроение и отношения."
