"""Система настроений Ноти."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List


class Mood(Enum):
    PLAYFUL = "playful"
    IRRITATED = "irritated"
    BORED = "bored"
    CURIOUS = "curious"
    TIRED = "tired"
    NEUTRAL = "neutral"


class MoodManager:
    def __init__(self, initial_mood: Mood = Mood.NEUTRAL, initial_energy: int = 100):
        self.current_mood = initial_mood
        self.energy = initial_energy
        self.interactions_since_last_sleep = 0
        self.mood_history: List[Dict[str, Any]] = []

    def update_on_event(self, event_type: str, event_data: Dict[str, Any] | None = None):
        event_data = event_data or {}
        self.energy = max(0, self.energy - event_data.get("energy_cost", 1))
        self.interactions_since_last_sleep += 1

        if event_type == "praised":
            self._shift_mood_towards(Mood.PLAYFUL, 2)
        elif event_type == "insulted":
            self._shift_mood_towards(Mood.IRRITATED, 3)
        elif event_type == "boring_conversation":
            self._shift_mood_towards(Mood.BORED, 1)
        elif event_type == "interesting_topic":
            self._shift_mood_towards(Mood.CURIOUS, 2)
        elif event_type == "conflict_observed":
            self._shift_mood_towards(Mood.PLAYFUL, 1)

        if self.energy < 20:
            self.current_mood = Mood.TIRED
        if self.interactions_since_last_sleep > 100:
            self._shift_mood_towards(Mood.TIRED, 2)
        if 0 <= datetime.now().hour < 6:
            self._shift_mood_towards(Mood.TIRED, 1)

        self._log_mood_change(event_type, event_data)

    def _shift_mood_towards(self, target_mood: Mood, strength: int = 1):
        if random.random() < strength * 0.3:
            self.current_mood = target_mood

    def should_sleep(self) -> bool:
        return self.energy < 10 or self.current_mood == Mood.TIRED or self.interactions_since_last_sleep > 150

    def sleep(self, hours: float = 2.0):
        self.energy = 100
        self.current_mood = Mood.NEUTRAL
        self.interactions_since_last_sleep = 0
        self._log_mood_change("sleep", {"hours": hours})

    def _log_mood_change(self, trigger: str, data: Dict[str, Any]):
        self.mood_history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "mood": self.current_mood.value,
                "energy": self.energy,
                "trigger": trigger,
                "data": data,
            }
        )
        if len(self.mood_history) > 100:
            self.mood_history = self.mood_history[-100:]

    def get_current_state(self) -> Dict[str, Any]:
        return {
            "mood": self.current_mood.value,
            "energy": self.energy,
            "interactions_today": self.interactions_since_last_sleep,
            "should_sleep": self.should_sleep(),
        }

    def get_mood_stats(self, hours: int = 24) -> Dict[str, Any]:
        cutoff = datetime.now() - timedelta(hours=hours)
        recent_moods = [m for m in self.mood_history if datetime.fromisoformat(m["timestamp"]) > cutoff]
        if not recent_moods:
            return {"error": "No data"}
        mood_counts: Dict[str, int] = {}
        for entry in recent_moods:
            mood_counts[entry["mood"]] = mood_counts.get(entry["mood"], 0) + 1
        avg_energy = sum(e["energy"] for e in recent_moods) / len(recent_moods)
        return {
            "period_hours": hours,
            "mood_distribution": mood_counts,
            "average_energy": avg_energy,
            "total_changes": len(recent_moods),
        }
