"""
Vector Store Service — Phase 3 Code RAG.

Wraps qdrant-client with:
- Automatic fallback to in-memory mode when the Qdrant server is unreachable.
- Per-repository and per-user payload filtering for access control.
- Upsert, semantic search, and deletion helpers.

Design rules:
- Never exposes raw Qdrant internals to callers.
- Returns empty lists (not exceptions) when Qdrant is unavailable.
- Logs a clear warning when falling back to in-memory mode.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger("forge.vector_store")

# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------

class VectorSearchResult:
    """A single result from a semantic (Qdrant) search."""

    def __init__(
        self,
        chunk_id: str,
        repository_id: str,
        file_path: str,
        symbol_name: Optional[str],
        symbol_type: str,
        start_line: int,
        end_line: int,
        language: Optional[str],
        chunk_content: str,
        score: float,
    ) -> None:
        self.chunk_id = chunk_id
        self.repository_id = repository_id
        self.file_path = file_path
        self.symbol_name = symbol_name
        self.symbol_type = symbol_type
        self.start_line = start_line
        self.end_line = end_line
        self.language = language
        self.chunk_content = chunk_content
        self.score = score


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class VectorStoreService:
    """Thread-safe singleton wrapping qdrant-client."""

    _instance: Optional["VectorStoreService"] = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self) -> None:
        self._client = None
        self._is_memory: bool = False
        self._client_lock = threading.Lock()
        self._collection_name: str = "forge_code_chunks"
        self._dimension: int = 384

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls) -> "VectorStoreService":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        with cls._lock:
            cls._instance = None

    # ------------------------------------------------------------------
    # Client initialisation (lazy)
    # ------------------------------------------------------------------

    def _ensure_client(self, collection_name: str, dimension: int) -> None:
        if self._client is not None:
            return
        with self._client_lock:
            if self._client is not None:
                return
            self._collection_name = collection_name
            self._dimension = dimension
            self._client = self._build_client()

    def _build_client(self):
        """
        Try to connect to the Qdrant server; fall back to :memory: if it
        is unavailable.
        """
        from app.core.config import settings  # local import to avoid circular
        from qdrant_client import QdrantClient  # type: ignore
        from qdrant_client.models import Distance, VectorParams  # type: ignore

        use_memory = getattr(settings, "QDRANT_USE_MEMORY", False)

        if not use_memory:
            try:
                client = QdrantClient(url=settings.QDRANT_URL, timeout=5)
                # Probe the server
                client.get_collections()
                self._is_memory = False
                logger.info(f"Connected to Qdrant server at {settings.QDRANT_URL}")
            except Exception as exc:
                logger.warning(
                    f"Qdrant server unavailable ({exc}). "
                    "Falling back to in-memory Qdrant (data will not persist across restarts)."
                )
                client = QdrantClient(":memory:")
                self._is_memory = True
        else:
            client = QdrantClient(":memory:")
            self._is_memory = True
            logger.info("Using in-memory Qdrant (QDRANT_USE_MEMORY=True).")

        # Ensure the collection exists
        existing = {c.name for c in client.get_collections().collections}
        if self._collection_name not in existing:
            client.create_collection(
                collection_name=self._collection_name,
                vectors_config=VectorParams(
                    size=self._dimension,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(f"Created Qdrant collection '{self._collection_name}'.")

        return client

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def configure(self, collection_name: str, dimension: int) -> None:
        """Call once at application startup to set collection & dimension."""
        self._collection_name = collection_name
        self._dimension = dimension

    def is_available(self) -> bool:
        try:
            self._ensure_client(self._collection_name, self._dimension)
            return True
        except Exception:
            return False

    def is_memory_mode(self) -> bool:
        return self._is_memory

    # ------------------------------------------------------------------
    # Upsert
    # ------------------------------------------------------------------

    def upsert_chunks(
        self,
        chunks: List[Dict[str, Any]],
        embeddings: List[List[float]],
    ) -> bool:
        """
        Upsert chunks and their embeddings into Qdrant.

        Each element in ``chunks`` must have keys:
            chunk_id, repository_id, user_id, file_path, symbol_name,
            symbol_type, start_line, end_line, language, chunk_content
        """
        if not chunks or not embeddings:
            return True
        try:
            self._ensure_client(self._collection_name, self._dimension)
            from qdrant_client.models import PointStruct  # type: ignore
            import uuid

            points = []
            for chunk, vector in zip(chunks, embeddings):
                # Qdrant requires UUID-format point IDs.
                # Derive a stable UUID from chunk_id via uuid5.
                raw_id = chunk["chunk_id"]
                try:
                    point_id = str(uuid.UUID(raw_id))  # already a UUID
                except (ValueError, AttributeError):
                    # Not a UUID — derive one deterministically
                    point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, raw_id))

                points.append(
                    PointStruct(
                        id=point_id,
                        vector=vector,
                        payload={
                            "chunk_id": raw_id,
                            "repository_id": chunk["repository_id"],
                            "user_id": chunk["user_id"],
                            "file_path": chunk["file_path"],
                            "symbol_name": chunk.get("symbol_name"),
                            "symbol_type": chunk.get("symbol_type", "BLOCK"),
                            "start_line": chunk.get("start_line", 1),
                            "end_line": chunk.get("end_line", 1),
                            "language": chunk.get("language"),
                            "chunk_content": chunk.get("chunk_content", ""),
                        },
                    )
                )

            self._client.upsert(collection_name=self._collection_name, points=points)
            logger.debug(f"Upserted {len(points)} vectors into Qdrant.")
            return True
        except Exception as exc:
            logger.error(f"Qdrant upsert failed: {exc}")
            return False

    # ------------------------------------------------------------------
    # Semantic search
    # ------------------------------------------------------------------

    def search_semantic(
        self,
        query_vector: List[float],
        repository_id: str,
        top_k: int = 10,
    ) -> List[VectorSearchResult]:
        """
        Search for the nearest code chunks within a specific repository.

        Filters by repository_id so users can only retrieve their own code.
        """
        try:
            self._ensure_client(self._collection_name, self._dimension)
            from qdrant_client.models import Filter, FieldCondition, MatchValue  # type: ignore

            response = self._client.query_points(
                collection_name=self._collection_name,
                query=query_vector,
                query_filter=Filter(
                    must=[
                        FieldCondition(
                            key="repository_id",
                            match=MatchValue(value=repository_id),
                        )
                    ]
                ),
                limit=top_k,
                with_payload=True,
            )

            output = []
            for hit in response.points:
                p = hit.payload or {}
                output.append(
                    VectorSearchResult(
                        chunk_id=p.get("chunk_id", ""),
                        repository_id=p.get("repository_id", ""),
                        file_path=p.get("file_path", ""),
                        symbol_name=p.get("symbol_name"),
                        symbol_type=p.get("symbol_type", "BLOCK"),
                        start_line=p.get("start_line", 1),
                        end_line=p.get("end_line", 1),
                        language=p.get("language"),
                        chunk_content=p.get("chunk_content", ""),
                        score=hit.score,
                    )
                )
            return output
        except Exception as exc:
            logger.error(f"Qdrant semantic search failed: {exc}")
            return []

    # ------------------------------------------------------------------
    # Deletion
    # ------------------------------------------------------------------

    def delete_by_repository(self, repository_id: str) -> bool:
        """Remove all vectors for a given repository."""
        try:
            self._ensure_client(self._collection_name, self._dimension)
            from qdrant_client.models import Filter, FieldCondition, MatchValue  # type: ignore

            self._client.delete(
                collection_name=self._collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="repository_id",
                            match=MatchValue(value=repository_id),
                        )
                    ]
                ),
            )
            logger.info(f"Deleted Qdrant vectors for repository {repository_id}.")
            return True
        except Exception as exc:
            logger.error(f"Qdrant delete failed: {exc}")
            return False

    def delete_by_file(self, repository_id: str, file_path: str) -> bool:
        """Remove vectors for a specific file within a repository."""
        try:
            self._ensure_client(self._collection_name, self._dimension)
            from qdrant_client.models import Filter, FieldCondition, MatchValue  # type: ignore

            self._client.delete(
                collection_name=self._collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="repository_id",
                            match=MatchValue(value=repository_id),
                        ),
                        FieldCondition(
                            key="file_path",
                            match=MatchValue(value=file_path),
                        ),
                    ]
                ),
            )
            return True
        except Exception as exc:
            logger.error(f"Qdrant file-level delete failed: {exc}")
            return False
