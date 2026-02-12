"""Сущности governance для изменений personality."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class PersonalityProposal:
    proposal_id: str
    author: str
    diff_summary: str
    risk: str
    new_personality_text: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ApprovalDecision:
    proposal_id: str
    reviewer: str
    decision: str
    reason: str
    decided_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RollbackEvent:
    proposal_id: str
    from_version: int
    to_version: int
    trigger: str
    kpi_before: dict[str, float]
    kpi_after: dict[str, float]
    happened_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
