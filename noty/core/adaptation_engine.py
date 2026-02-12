"""Адаптация тона Ноти по сигналам взаимодействий."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class AdaptationRecommendation:
    preferred_tone: str
    sarcasm_level: float
    response_rate_bias: float
    reason: str
    signal_source: str
    rollback_required: bool = False


class AdaptationEngine:
    """Генерирует рекомендации по корректировке personality на основе фидбэка."""

    def recommend(
        self,
        interaction_outcome: str,
        user_feedback_signals: Dict[str, Any],
        relationship_trend: Dict[str, Any],
        filter_stats: Dict[str, Any],
    ) -> AdaptationRecommendation:
        score = float(relationship_trend.get("score", 0))
        positive_ratio = float(relationship_trend.get("positive_ratio", 0.5))
        negative_streak = int(relationship_trend.get("negative_streak", 0))

        decider_stats = filter_stats.get("decider", {})
        response_rate = float(decider_stats.get("respond_rate", 0.0))
        target_rate = 0.2
        response_rate_bias = max(-0.2, min(0.2, target_rate - response_rate))

        explicit_sentiment = str(user_feedback_signals.get("sentiment", "neutral"))
        if interaction_outcome == "success" and explicit_sentiment != "negative" and positive_ratio >= 0.65:
            preferred_tone = "playful"
            sarcasm_level = 0.65
            reason = "Стабильно положительная реакция и хороший relationship trend"
        elif interaction_outcome != "success" or explicit_sentiment == "negative" or negative_streak >= 2:
            preferred_tone = "dry"
            sarcasm_level = 0.2
            reason = "Негативный исход/фидбэк — понижаем язвительность"
        elif score <= -3:
            preferred_tone = "neutral"
            sarcasm_level = 0.3
            reason = "Низкий relationship score — умеренный тон"
        else:
            preferred_tone = "medium_sarcasm"
            sarcasm_level = 0.45
            reason = "Баланс без явных сигналов в обе стороны"

        signal_parts = [f"outcome={interaction_outcome}", f"feedback={explicit_sentiment}", f"neg_streak={negative_streak}"]
        rollback_required = negative_streak >= 3
        if rollback_required:
            reason += "; включён rollback-защитный контур"

        return AdaptationRecommendation(
            preferred_tone=preferred_tone,
            sarcasm_level=sarcasm_level,
            response_rate_bias=response_rate_bias,
            reason=reason,
            signal_source=", ".join(signal_parts),
            rollback_required=rollback_required,
        )
