"""Калибратор вероятности ответа: эвристика + embeddings + рандомизация."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict


@dataclass
class ReactionDecision:
    should_respond: bool
    score: float
    threshold: float
    sampled_probability: float
    reason: str


class ReactionDecider:
    def __init__(self, target_rate: float = 0.2, min_threshold: float = 0.35, max_threshold: float = 0.8):
        self.target_rate = target_rate
        self.min_threshold = min_threshold
        self.max_threshold = max_threshold
        self._seen = 0
        self._responded = 0

    def _adaptive_threshold(self) -> float:
        if self._seen == 0:
            return 0.5
        current_rate = self._responded / self._seen
        drift = current_rate - self.target_rate
        adjusted = 0.5 + drift * 0.6
        return max(self.min_threshold, min(self.max_threshold, adjusted))

    def decide(self, semantic_score: float, heuristic_boost: float = 0.0) -> ReactionDecision:
        self._seen += 1
        threshold = self._adaptive_threshold()

        calibrated_score = min(1.0, max(0.0, semantic_score + heuristic_boost))
        if calibrated_score < threshold:
            return ReactionDecision(False, calibrated_score, threshold, 0.0, "below_threshold")

        probability = min(1.0, 0.4 + calibrated_score * 0.6)
        sampled = random.random()
        should = sampled < probability
        if should:
            self._responded += 1
        return ReactionDecision(
            should_respond=should,
            score=calibrated_score,
            threshold=threshold,
            sampled_probability=probability,
            reason="sampled_in" if should else "sampled_out",
        )

    def stats(self) -> Dict[str, float]:
        response_rate = (self._responded / self._seen) if self._seen else 0.0
        return {
            "seen": float(self._seen),
            "responded": float(self._responded),
            "response_rate": round(response_rate, 4),
            "target_rate": self.target_rate,
            "adaptive_threshold": round(self._adaptive_threshold(), 4),
        }
