from __future__ import annotations

from sentence_transformers import SentenceTransformer

from src.config import settings


class EmbeddingService:
    """Wraps a SentenceTransformer model for text embedding."""

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or settings.embedding_model
        self._model: SentenceTransformer | None = None

    def _load(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed(self, text: str) -> list[float]:
        model = self._load()
        vector = model.encode(text, normalize_embeddings=True)
        return vector.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        vectors = model.encode(texts, normalize_embeddings=True, batch_size=32)
        return vectors.tolist()

    @property
    def dimension(self) -> int:
        model = self._load()
        return model.get_sentence_embedding_dimension()
