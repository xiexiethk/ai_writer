import sys

import numpy as np

sys.path.insert(0, "backend")

from app.services import embedding as embedding_module


def _build_service(monkeypatch: object) -> embedding_module.EmbeddingService:
    monkeypatch.setattr(embedding_module.EmbeddingService, "_initialize_dimension", lambda self: None)
    service = embedding_module.EmbeddingService()
    service.batch_size = 32
    service.max_retries = 0
    return service


def test_encode_with_indices_uses_batch_requests(monkeypatch):
    service = _build_service(monkeypatch)
    calls = []

    def fake_embedding_request(texts, *, provider=None, model=None, timeout=60.0):
        calls.append(texts)
        items = [texts] if isinstance(texts, str) else list(texts)
        return [[float(index), float(index + 1)] for index, _ in enumerate(items)]

    monkeypatch.setattr(embedding_module, "embedding_request", fake_embedding_request)

    texts = [f"text-{index}" for index in range(40)]
    successful_indices, embeddings = service.encode_with_indices(texts)

    assert successful_indices == list(range(40))
    assert embeddings.shape == (40, 2)
    assert isinstance(calls[0], list)
    assert isinstance(calls[1], list)
    assert len(calls[0]) == 32
    assert len(calls[1]) == 8


def test_encode_with_indices_falls_back_to_single_requests(monkeypatch):
    service = _build_service(monkeypatch)
    calls = []

    def fake_embedding_request(texts, *, provider=None, model=None, timeout=60.0):
        calls.append(texts)
        if isinstance(texts, list):
            raise RuntimeError("batch failed")
        return [[float(len(texts)), float(len(texts) + 1)]]

    monkeypatch.setattr(embedding_module, "embedding_request", fake_embedding_request)
    monkeypatch.setattr(embedding_module.time, "sleep", lambda _: None)

    texts = ["aa", "bbb", "cccc"]
    successful_indices, embeddings = service.encode_with_indices(texts)

    assert successful_indices == [0, 1, 2]
    np.testing.assert_array_equal(
        embeddings,
        np.array([[2.0, 3.0], [3.0, 4.0], [4.0, 5.0]], dtype=np.float32),
    )
    assert calls == [texts, "aa", "bbb", "cccc"]
