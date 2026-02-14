"""Выделение, валидация и хранение псевдонимов/прозвищ пользователей."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, List


@dataclass
class AliasExtractionResult:
    aliases: List[Dict[str, Any]]
    should_ask_confirmation: bool


class UserAliasManager:
    def __init__(self, db_manager: Any, min_confidence: float = 0.5):
        self.db = db_manager
        self.min_confidence = min_confidence

    @staticmethod
    def _normalize(alias: str) -> str:
        alias = re.sub(r"[^\wа-яА-ЯёЁ-]", "", alias.lower()).strip("-")
        return alias

    def extract_alias_signals(self, text: str, user_id: int | None = None) -> AliasExtractionResult:
        lowered = text.lower()
        aliases: List[Dict[str, Any]] = []

        patterns = [
            r"зов[иу] меня\s+([\wа-яА-ЯёЁ-]{2,32})",
            r"можешь звать меня\s+([\wа-яА-ЯёЁ-]{2,32})",
            r"я\s+([\wа-яА-ЯёЁ-]{2,32}),\s*но.*зовут\s+([\wа-яА-ЯёЁ-]{2,32})",
            r"это\s+([\wа-яА-ЯёЁ-]{2,32}),\s*его\s+кличка\s+([\wа-яА-ЯёЁ-]{2,32})",
            r"мой ник\s+([\wа-яА-ЯёЁ-]{2,32})",
        ]

        for pattern in patterns:
            for match in re.findall(pattern, lowered):
                if isinstance(match, tuple):
                    candidate = match[-1]
                else:
                    candidate = match
                normalized = self._normalize(candidate)
                if len(normalized) < 2:
                    continue
                aliases.append(
                    {
                        "user_id": user_id,
                        "alias": candidate,
                        "normalized_alias": normalized,
                        "confidence": 0.72,
                        "source": "heuristic",
                        "is_verified": "зови" in lowered or "можешь звать" in lowered,
                    }
                )

        should_ask = bool(
            re.search(r"это\s+([\wа-яА-ЯёЁ-]{2,32}),\s*его\s+кличка", lowered)
            and not re.search(r"подтверждаю|точно|верно", lowered)
        )
        dedup: Dict[str, Dict[str, Any]] = {}
        for item in aliases:
            key = item["normalized_alias"]
            prev = dedup.get(key)
            if not prev or float(item["confidence"]) > float(prev["confidence"]):
                dedup[key] = item

        return AliasExtractionResult(aliases=list(dedup.values()), should_ask_confirmation=should_ask)

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

    def extract_and_persist(self, *, chat_id: int, user_id: int, text: str) -> AliasExtractionResult:
        result = self.extract_alias_signals(text=text, user_id=user_id)
        self.persist_aliases(chat_id=chat_id, user_id=user_id, aliases=result.aliases)
        return result

    def get_preferred_alias(self, *, chat_id: int, user_id: int) -> str | None:
        verified = self.db.list_user_aliases(chat_id=chat_id, user_id=user_id, only_verified=True)
        if verified:
            return verified[0]["alias"]
        items = self.db.list_user_aliases(chat_id=chat_id, user_id=user_id, only_verified=False)
        return items[0]["alias"] if items else None

    def list_aliases(self, *, chat_id: int, user_id: int) -> List[Dict[str, Any]]:
        return self.db.list_user_aliases(chat_id=chat_id, user_id=user_id, only_verified=False)
