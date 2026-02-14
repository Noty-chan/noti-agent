"""Профиль персоны пользователя и обновление из диалоговых сигналов."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any, Callable, Dict, List


@dataclass
class UserPersonaProfile:
    preferred_style: str = "balanced"
    sarcasm_tolerance: float = 0.5
    taboo_topics: List[str] = field(default_factory=list)
    motivators: List[str] = field(default_factory=list)
    response_depth_preference: str = "medium"
    confidence: float = 0.0
    source: str = "default"

    def compact_slice(self) -> Dict[str, Any]:
        return {
            "preferred_style": self.preferred_style,
            "sarcasm_tolerance": round(self.sarcasm_tolerance, 3),
            "taboo_topics": self.taboo_topics[:4],
            "motivators": self.motivators[:4],
            "response_depth_preference": self.response_depth_preference,
            "confidence": round(self.confidence, 3),
            "source": self.source,
        }


class PersonaProfileManager:
    """Обновляет persona-профиль комбинацией эвристик и LLM extraction."""

    @staticmethod
    def _validate_style(value: Any) -> str | None:
        if value is None:
            return None
        allowed = {"balanced", "supportive", "sarcastic", "neutral"}
        val = str(value).strip().lower()
        return val if val in allowed else None

    @staticmethod
    def _validate_depth(value: Any) -> str | None:
        if value is None:
            return None
        allowed = {"short", "medium", "deep"}
        val = str(value).strip().lower()
        return val if val in allowed else None

    def __init__(
        self,
        db_manager: Any,
        llm_extractor: Callable[[str], Dict[str, Any]] | None = None,
        min_llm_confidence: float = 0.55,
        min_profile_confidence: float = 0.4,
    ):
        self.db = db_manager
        self.llm_extractor = llm_extractor
        self.min_llm_confidence = min_llm_confidence
        self.min_profile_confidence = min_profile_confidence

    def get_profile(self, user_id: int, chat_id: int) -> UserPersonaProfile:
        payload = self.db.get_user_persona_profile(user_id=user_id, chat_id=chat_id)
        if not payload:
            return UserPersonaProfile()
        return UserPersonaProfile(**payload)

    def update_from_dialogue(self, *, user_id: int, chat_id: int, text: str) -> UserPersonaProfile:
        existing = self.get_profile(user_id=user_id, chat_id=chat_id)
        heuristic = self._heuristic_extract(text)
        llm = self._llm_extract(text)

        merged = self._merge_signals(existing, heuristic, llm)
        self.db.upsert_user_persona_profile(user_id=user_id, chat_id=chat_id, profile=merged.__dict__)
        return merged

    def should_use_conservative_fallback(self, profile: UserPersonaProfile) -> bool:
        return profile.confidence < self.min_profile_confidence

    @staticmethod
    def _heuristic_extract(text: str) -> Dict[str, Any]:
        lowered = text.lower()
        preferred_style = None
        if any(marker in lowered for marker in ("без сарказма", "помягче", "вежлив")):
            preferred_style = "supportive"
        elif any(marker in lowered for marker in ("жестче", "поострее", "саркастич")):
            preferred_style = "sarcastic"

        depth = None
        if any(marker in lowered for marker in ("кратко", "короче", "в двух словах")):
            depth = "short"
        elif any(marker in lowered for marker in ("подробно", "детально", "по шагам")):
            depth = "deep"

        taboo_markers = re.findall(r"не говори про ([\w\- ]+)", lowered)
        motivators = []
        if "важно" in lowered:
            motivators.append("importance")
        if "дедлайн" in lowered:
            motivators.append("deadline")

        sarcasm_tolerance = None
        if "без сарказма" in lowered:
            sarcasm_tolerance = 0.15
        elif "можно сарказм" in lowered or "сарказм ок" in lowered:
            sarcasm_tolerance = 0.8

        return {
            "preferred_style": preferred_style,
            "sarcasm_tolerance": sarcasm_tolerance,
            "taboo_topics": [topic.strip() for topic in taboo_markers if topic.strip()],
            "motivators": motivators,
            "response_depth_preference": depth,
            "confidence": 0.45 if any((preferred_style, depth, taboo_markers, motivators, sarcasm_tolerance is not None)) else 0.0,
            "source": "heuristic",
        }

    def _llm_extract(self, text: str) -> Dict[str, Any]:
        if not self.llm_extractor:
            return {}
        payload = self.llm_extractor(text) or {}
        confidence = float(payload.get("confidence", 0.0))
        if confidence < self.min_llm_confidence:
            return {}

        taboo_topics = payload.get("taboo_topics", [])
        motivators = payload.get("motivators", [])
        return {
            "preferred_style": self._validate_style(payload.get("preferred_style")),
            "sarcasm_tolerance": payload.get("sarcasm_tolerance"),
            "taboo_topics": [str(x).strip() for x in taboo_topics if str(x).strip()],
            "motivators": [str(x).strip() for x in motivators if str(x).strip()],
            "response_depth_preference": self._validate_depth(payload.get("response_depth_preference")),
            "confidence": confidence,
            "source": "llm",
        }

    @staticmethod
    def _merge_signals(existing: UserPersonaProfile, heuristic: Dict[str, Any], llm: Dict[str, Any]) -> UserPersonaProfile:
        merged = UserPersonaProfile(**existing.__dict__)

        for signal in (heuristic, llm):
            if not signal:
                continue
            if signal.get("preferred_style"):
                merged.preferred_style = signal["preferred_style"]
            if signal.get("sarcasm_tolerance") is not None:
                merged.sarcasm_tolerance = min(max(float(signal["sarcasm_tolerance"]), 0.0), 1.0)
            if signal.get("response_depth_preference"):
                merged.response_depth_preference = signal["response_depth_preference"]
            for topic in signal.get("taboo_topics", []):
                if topic not in merged.taboo_topics:
                    merged.taboo_topics.append(topic)
            for motivator in signal.get("motivators", []):
                if motivator not in merged.motivators:
                    merged.motivators.append(motivator)

        h_conf = float(heuristic.get("confidence", 0.0))
        llm_conf = float(llm.get("confidence", 0.0))
        if h_conf and llm_conf:
            merged.confidence = round((h_conf * 0.4) + (llm_conf * 0.6), 3)
            merged.source = "hybrid"
        elif llm_conf:
            merged.confidence = round(llm_conf, 3)
            merged.source = "llm"
        elif h_conf:
            merged.confidence = round(h_conf, 3)
            merged.source = "heuristic"
        return merged


def profile_to_json(profile: UserPersonaProfile) -> str:
    return json.dumps(profile.compact_slice(), ensure_ascii=False)
