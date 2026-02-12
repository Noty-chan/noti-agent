"""Семантическая фильтрация сообщений по близости к интересам."""

from __future__ import annotations

import os
import pickle
from typing import Dict, Iterable, List, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer

from .interest_vectors import INTEREST_TOPICS


class EmbeddingFilter:
    def __init__(
        self,
        model_name: str = "intfloat/multilingual-e5-base",
        cache_path: str = "./noty/data/embeddings_cache",
        encoder: SentenceTransformer | None = None,
    ):
        self.encoder = encoder or SentenceTransformer(model_name)
        self.cache_path = cache_path
        os.makedirs(cache_path, exist_ok=True)
        self.interest_topics = INTEREST_TOPICS
        self.interest_vectors = self._load_or_create_interest_vectors()
        self._message_vector_cache: Dict[str, np.ndarray] = {}
        self.cache_hits = 0
        self.cache_misses = 0

    def _load_or_create_interest_vectors(self) -> np.ndarray:
        cache_file = os.path.join(self.cache_path, "interest_vectors.pkl")
        if os.path.exists(cache_file):
            with open(cache_file, "rb") as file:
                return pickle.load(file)

        vectors = self.encoder.encode(self.interest_topics, convert_to_numpy=True, show_progress_bar=True)
        with open(cache_file, "wb") as file:
            pickle.dump(vectors, file)
        return vectors

    def _vectorize_messages(self, messages: Iterable[str]) -> Dict[str, np.ndarray]:
        unique_messages = list(dict.fromkeys(messages))
        result: Dict[str, np.ndarray] = {}
        uncached = [message for message in unique_messages if message not in self._message_vector_cache]

        self.cache_hits += len(unique_messages) - len(uncached)
        self.cache_misses += len(uncached)

        if uncached:
            encoded = self.encoder.encode(uncached, convert_to_numpy=True)
            if isinstance(encoded, np.ndarray) and encoded.ndim == 1:
                encoded = np.array([encoded])
            for message, vector in zip(uncached, encoded):
                self._message_vector_cache[message] = vector

        for message in unique_messages:
            result[message] = self._message_vector_cache[message]
        return result

    def _best_topic_similarity(self, msg_vector: np.ndarray) -> Tuple[str, float]:
        similarities = []
        for i, interest_vec in enumerate(self.interest_vectors):
            sim = np.dot(msg_vector, interest_vec) / (
                np.linalg.norm(msg_vector) * np.linalg.norm(interest_vec)
            )
            similarities.append((self.interest_topics[i], sim))
        return max(similarities, key=lambda x: x[1])

    def is_interesting(
        self,
        message: str,
        threshold: float = 0.4,
        return_score: bool = False,
    ) -> bool | Tuple[bool, float, str]:
        msg_vector = self._vectorize_messages([message])[message]
        best_topic, best_score = self._best_topic_similarity(msg_vector)
        is_interesting = best_score > threshold
        if return_score:
            return is_interesting, float(best_score), best_topic
        return is_interesting

    def batch_filter(self, messages: List[str], threshold: float = 0.4) -> List[Tuple[int, str, float, str]]:
        results: List[Tuple[int, str, float, str]] = []
        vectors = self._vectorize_messages(messages)
        for i, msg in enumerate(messages):
            best_topic, best_score = self._best_topic_similarity(vectors[msg])
            if best_score > threshold:
                results.append((i, msg, float(best_score), best_topic))
        return results

    def cache_stats(self) -> Dict[str, float]:
        total = self.cache_hits + self.cache_misses
        hit_rate = (self.cache_hits / total) if total else 0.0
        return {
            "hits": self.cache_hits,
            "misses": self.cache_misses,
            "hit_rate": round(hit_rate, 4),
        }
