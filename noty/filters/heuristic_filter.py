"""Быстрый эвристический фильтр, отсекающий шум до embedding-проверки."""

from __future__ import annotations

import random
import re


class HeuristicFilter:
    def __init__(self, pass_probability: float = 0.2):
        self.pass_probability = pass_probability
        self.keywords = {
            "noty",
            "ноти",
            "почему",
            "как",
            "зачем",
            "философ",
            "код",
            "программ",
            "конфликт",
            "спор",
        }

    def should_check_embeddings(self, message: str) -> bool:
        text = message.lower().strip()
        if not text:
            return False
        if len(text) < 3:
            return False
        if any(word in text for word in self.keywords):
            return True
        if re.search(r"\?$", text):
            return True
        return random.random() < self.pass_probability
