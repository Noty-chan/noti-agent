import numpy as np

from noty.filters.embedding_filter import EmbeddingFilter


class FakeEncoder:
    def __init__(self):
        self.calls = 0

    def encode(self, texts, convert_to_numpy=True, show_progress_bar=False):
        self.calls += 1
        if isinstance(texts, str):
            return np.array([1.0, float(len(texts))])
        return np.array([[1.0, float(len(text))] for text in texts])


def test_embedding_filter_cache_hit_and_batching(tmp_path):
    encoder = FakeEncoder()
    filt = EmbeddingFilter(cache_path=str(tmp_path), encoder=encoder)

    before = encoder.calls
    filt.is_interesting("hello", threshold=-1)
    first_after = encoder.calls
    filt.is_interesting("hello", threshold=-1)
    second_after = encoder.calls

    assert first_after - before == 1
    assert second_after == first_after

    batch_before = encoder.calls
    filt.batch_filter(["a", "bb", "a", "ccc"], threshold=-1)
    batch_after = encoder.calls

    assert batch_after - batch_before == 1
    stats = filt.cache_stats()
    assert stats["hits"] >= 1
    assert stats["hit_rate"] > 0
