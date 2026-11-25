"""
Embedding Service — Phase 3 Code RAG.

Wraps sentence-transformers with a lazy singleton pattern so the model is
loaded once and reused across requests.  Uses all-MiniLM-L6-v2 by default
(384 dimensions, CPU-friendly, ~22 MB on disk).

Never uses random / fake vectors.  Raises EmbeddingUnavailableError when
the model cannot be loaded so callers can surface a clear error message.
"""
from __future__ import annotations

import logging
import threading
from typing import List, Optional

logger = logging.getLogger("forge.embedding")


class EmbeddingUnavailableError(RuntimeError):
    """Raised when the sentence-transformers model could not be initialised."""


class EmbeddingService:
    """Thread-safe singleton wrapper around a sentence-transformers model."""

    _instance: Optional["EmbeddingService"] = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._model = None          # loaded lazily on first use
        self._model_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Singleton factory
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls, model_name: str = "all-MiniLM-L6-v2") -> "EmbeddingService":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(model_name)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Used in tests to swap the model out."""
        with cls._lock:
            cls._instance = None

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _ensure_model(self) -> None:
        """Lazy-load the sentence-transformers model (once per process)."""
        if self._model is not None:
            return
        with self._model_lock:
            if self._model is not None:
                return
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore
                logger.info(f"Loading embedding model: {self._model_name}")
                self._model = SentenceTransformer(self._model_name)
                logger.info(
                    f"Embedding model loaded. "
                    f"Dimension: {self._model.get_sentence_embedding_dimension()}"
                )
            except Exception as exc:
                logger.error(f"Failed to load embedding model '{self._model_name}': {exc}")
                raise EmbeddingUnavailableError(
                    f"Could not load sentence-transformers model '{self._model_name}'. "
                    f"Reason: {exc}"
                ) from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def model_name(self) -> str:
        return self._model_name

    def get_dimension(self) -> int:
        """Return the embedding dimension.  Loads the model if necessary."""
        self._ensure_model()
        return self._model.get_sentence_embedding_dimension()  # type: ignore[union-attr]

    def encode_batch(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """
        Encode a list of texts into dense embedding vectors.

        Args:
            texts: Non-empty list of strings.
            batch_size: Mini-batch size passed to sentence-transformers.

        Returns:
            List of float lists, one per input text.

        Raises:
            EmbeddingUnavailableError: if the model is unavailable.
            ValueError: if texts is empty.
        """
        if not texts:
            raise ValueError("texts must be a non-empty list")
        self._ensure_model()
        logger.debug(f"Encoding {len(texts)} texts with batch_size={batch_size}")
        embeddings = self._model.encode(  # type: ignore[union-attr]
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,  # cosine similarity via dot product
        )
        return [emb.tolist() for emb in embeddings]

    def encode_single(self, text: str) -> List[float]:
        """Convenience wrapper for a single text."""
        return self.encode_batch([text])[0]

    def is_available(self) -> bool:
        """Return True if the model can be loaded without error."""
        try:
            self._ensure_model()
            return True
        except EmbeddingUnavailableError:
            return False
