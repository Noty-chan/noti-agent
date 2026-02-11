"""Семантическая фильтрация сообщений по близости к интересам."""

from __future__ import annotations

import os
import pickle
from typing import List, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer

from .interest_vectors import INTEREST_TOPICS


class EmbeddingFilter:
    def __init__(
        self,
        model_name: str = "intfloat/multilingual-e5-base",
        cache_path: str = "./noty/data/embeddings_cache",
    ):
        self.encoder = SentenceTransformer(model_name)
        self.cache_path = cache_path
        os.makedirs(cache_path, exist_ok=True)
        self.interest_topics = INTEREST_TOPICS
        self.interest_vectors = self._load_or_create_interest_vectors()

    def _load_or_create_interest_vectors(self) -> np.ndarray:
        cache_file = os.path.join(self.cache_path, "interest_vectors.pkl")
        if os.path.exists(cache_file):
            with open(cache_file, "rb") as file:
                return pickle.load(file)

        vectors = self.encoder.encode(self.interest_topics, convert_to_numpy=True, show_progress_bar=True)
        with open(cache_file, "wb") as file:
            pickle.dump(vectors, file)
        return vectors

    def is_interesting(
        self,
        message: str,
        threshold: float = 0.4,
        return_score: bool = False,
    ) -> bool | Tuple[bool, float, str]:
        msg_vector = self.encoder.encode(message, convert_to_numpy=True)
        similarities = []
        for i, interest_vec in enumerate(self.interest_vectors):
            sim = np.dot(msg_vector, interest_vec) / (
                np.linalg.norm(msg_vector) * np.linalg.norm(interest_vec)
            )
            similarities.append((self.interest_topics[i], sim))

        best_topic, best_score = max(similarities, key=lambda x: x[1])
        is_interesting = best_score > threshold
        if return_score:
            return is_interesting, best_score, best_topic
        return is_interesting

    def batch_filter(self, messages: List[str], threshold: float = 0.4) -> List[Tuple[int, str, float, str]]:
        results: List[Tuple[int, str, float, str]] = []
        for i, msg in enumerate(messages):
            is_int, score, topic = self.is_interesting(msg, threshold, return_score=True)
            if is_int:
                results.append((i, msg, score, topic))
        return results
