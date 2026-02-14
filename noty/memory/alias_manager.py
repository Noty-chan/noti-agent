"""Выделение, валидация и хранение псевдонимов/прозвищ пользователей."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Dict, List


@dataclass
class AliasExtractionResult:
    aliases: List[Dict[str, Any]]
    should_ask_confirmation: bool
    relation_signals: List[Dict[str, Any]] = field(default_factory=list)
    rejected_aliases: List[Dict[str, Any]] = field(default_factory=list)


class UserAliasManager:
    def __init__(self, db_manager: Any, min_confidence: float = 0.5):
        self.db = db_manager
        self.min_confidence = min_confidence
        self.rejected_roots = {
            "господин",
            "повелитель",
            "хозяин",
            "boss",
            "master",
            "lord",
            "король",
            "царь",
            "император",
        }

    @staticmethod
    def _normalize(alias: str) -> str:
        return re.sub(r"[^\wа-яА-ЯёЁ-]", "", alias.lower()).strip("-")

    @staticmethod
    def _extract_fragment(text: str, pattern: str, group: int = 1) -> List[str]:
        matches = []
        for found in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = found.group(group)
            if value:
                matches.append(value.strip())
        return matches

    def _is_alias_allowed(self, normalized_alias: str) -> bool:
        if not normalized_alias:
            return False
        if normalized_alias in self.rejected_roots:
            return False
        return not any(normalized_alias.startswith(f"{root}-") for root in self.rejected_roots)

    def extract_alias_signals(self, text: str, user_id: int | None = None) -> AliasExtractionResult:
        aliases: List[Dict[str, Any]] = []
        rejected_aliases: List[Dict[str, Any]] = []

        direct_patterns = [
            r"зов[иу] меня\s+([\wа-яА-ЯёЁ-]{2,32})",
            r"можешь звать меня\s+([\wа-яА-ЯёЁ-]{2,32})",
            r"мой ник\s+([\wа-яА-ЯёЁ-]{2,32})",
            r"моя кличка\s+([\wа-яА-ЯёЁ-]{2,32})",
        ]
        for pattern in direct_patterns:
            for candidate in self._extract_fragment(text, pattern):
                normalized = self._normalize(candidate)
                if len(normalized) < 2:
                    continue
                if not self._is_alias_allowed(normalized):
                    rejected_aliases.append(
                        {
                            "user_id": user_id,
                            "alias": candidate,
                            "normalized_alias": normalized,
                            "reason": "dominance_title",
                        }
                    )
                    continue
                aliases.append(
                    {
                        "user_id": user_id,
                        "alias": candidate,
                        "normalized_alias": normalized,
                        "confidence": 0.78,
                        "source": "heuristic_direct",
                        "is_verified": True,
                    }
                )

        relation_signals: List[Dict[str, Any]] = []
        relation_patterns = [
            r"это\s+([\wа-яА-ЯёЁ-]{2,32}),\s*его\s+кличка\s+([\wа-яА-ЯёЁ-]{2,32})",
            r"([\wа-яА-ЯёЁ-]{2,32})\s+также\s+зовут\s+([\wа-яА-ЯёЁ-]{2,32})",
            r"([\wа-яА-ЯёЁ-]{2,32})\s*=\s*([\wа-яА-ЯёЁ-]{2,32})",
        ]
        for pattern in relation_patterns:
            for found in re.finditer(pattern, text, flags=re.IGNORECASE):
                target_name = (found.group(1) or "").strip()
                alias = (found.group(2) or "").strip()
                normalized = self._normalize(alias)
                if len(normalized) < 2 or not self._is_alias_allowed(normalized):
                    continue
                relation_signals.append(
                    {
                        "reporter_user_id": user_id,
                        "target_display_name": target_name,
                        "alias": alias,
                        "normalized_alias": normalized,
                        "confidence": 0.64,
                        "source": "heuristic_relation",
                        "is_verified": False,
                    }
                )

        lowered = text.lower()
        should_ask = bool(
            relation_signals
            and not re.search(r"подтверждаю|точно|верно|да,\s*это\s*так", lowered)
        )

        dedup: Dict[str, Dict[str, Any]] = {}
        for item in aliases:
            key = item["normalized_alias"]
            prev = dedup.get(key)
            if not prev or float(item["confidence"]) > float(prev["confidence"]):
                dedup[key] = item

        return AliasExtractionResult(
            aliases=list(dedup.values()),
            should_ask_confirmation=should_ask,
            relation_signals=relation_signals,
            rejected_aliases=rejected_aliases,
        )

    def persist_aliases(self, chat_id: int, user_id: int, aliases: List[Dict[str, Any]]) -> None:
        for item in aliases:
            conf = float(item.get("confidence", 0.0))
            if conf < self.min_confidence:
                continue
            alias = str(item.get("alias", "")).strip()
            normalized_alias = str(item.get("normalized_alias", "")).strip()
            if not alias or not normalized_alias:
                continue
            self.db.upsert_user_alias(
                chat_id=chat_id,
                user_id=user_id,
                alias=alias,
                normalized_alias=normalized_alias,
                confidence=conf,
                source=str(item.get("source", "heuristic")),
                is_verified=bool(item.get("is_verified", False)),
            )

    def persist_relation_signals(self, chat_id: int, relation_signals: List[Dict[str, Any]]) -> None:
        for item in relation_signals:
            conf = float(item.get("confidence", 0.0))
            alias = str(item.get("alias", "")).strip()
            normalized_alias = str(item.get("normalized_alias", "")).strip()
            target_display_name = str(item.get("target_display_name", "")).strip()
            if conf < self.min_confidence or not alias or not normalized_alias or not target_display_name:
                continue
            self.db.upsert_alias_relation(
                chat_id=chat_id,
                reporter_user_id=int(item.get("reporter_user_id") or 0),
                target_display_name=target_display_name,
                alias=alias,
                normalized_alias=normalized_alias,
                confidence=conf,
                source=str(item.get("source", "heuristic_relation")),
                is_verified=bool(item.get("is_verified", False)),
            )

    def extract_and_persist(self, *, chat_id: int, user_id: int, text: str) -> AliasExtractionResult:
        result = self.extract_alias_signals(text=text, user_id=user_id)
        self.persist_aliases(chat_id=chat_id, user_id=user_id, aliases=result.aliases)
        self.persist_relation_signals(chat_id=chat_id, relation_signals=result.relation_signals)
        return result

    def get_preferred_alias(self, *, chat_id: int, user_id: int) -> str | None:
        verified = self.db.list_user_aliases(chat_id=chat_id, user_id=user_id, only_verified=True)
        if verified:
            return verified[0]["alias"]
        items = self.db.list_user_aliases(chat_id=chat_id, user_id=user_id, only_verified=False)
        return items[0]["alias"] if items else None

    def list_aliases(self, *, chat_id: int, user_id: int) -> List[Dict[str, Any]]:
        return self.db.list_user_aliases(chat_id=chat_id, user_id=user_id, only_verified=False)

    def list_relation_signals(self, *, chat_id: int) -> List[Dict[str, Any]]:
        return self.db.list_alias_relations(chat_id=chat_id)
