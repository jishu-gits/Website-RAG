# backend/app/services/vector_store.py
"""Vector store abstraction and FAISS implementation.

Provides an abstract base class `BaseVectorStore` to allow future migration
to Managed Vector Databases (e.g., Pinecone, Qdrant, Milvus) with minimal changes.

Also provides the default local `FAISSVectorStore` implementation with metadata persistence.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

try:
    import faiss
except ImportError as exc:
    raise ImportError(
        "faiss-cpu is required.  Install it with:  pip install faiss-cpu"
    ) from exc

from app.core.config import settings
from app.core.logger import logger
from app.services.chunking import DocumentChunk


# ---------------------------------------------------------------------------
# Base Interface
# ---------------------------------------------------------------------------
class BaseVectorStore(ABC):
    """Abstract interface for vector stores to enable easy swapping."""

    @abstractmethod
    def add(self, pairs: List[Tuple[DocumentChunk, List[float]]]) -> int:
        """Insert (chunk, vector) pairs into the store."""
        pass

    @abstractmethod
    def search(self, query_vector: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        """Return the *top_k* most similar chunks with metadata."""
        pass

    @abstractmethod
    def delete_by_chunk_ids(self, chunk_ids: List[str]) -> int:
        """Remove chunks by their IDs."""
        pass

    @property
    @abstractmethod
    def size(self) -> int:
        """Return total number of vectors in the store."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all entries from the store."""
        pass

    def save(self) -> None:
        """Optional hook to persist the store to disk (mainly for local stores)."""
        pass


# ---------------------------------------------------------------------------
# FAISS Implementation
# ---------------------------------------------------------------------------
_STORE_DIR = Path(settings.vector_store_path)
_INDEX_FILE = _STORE_DIR / "index.faiss"
_META_FILE = _STORE_DIR / "metadata.json"


class FAISSVectorStore(BaseVectorStore):
    """Local FAISS ``IndexFlatIP`` index with a metadata sidecar."""

    def __init__(self, dimension: int = 768) -> None:
        self.dimension = dimension
        self._index: faiss.IndexFlatIP = faiss.IndexFlatIP(dimension)
        self._metadata: List[Dict[str, Any]] = []
        self._id_to_row: Dict[str, int] = {}

        if _INDEX_FILE.exists() and _META_FILE.exists():
            self._load()

    def add(self, pairs: List[Tuple[DocumentChunk, List[float]]]) -> int:
        vectors_to_add: List[List[float]] = []
        metas_to_add: List[Dict[str, Any]] = []

        for chunk, vector in pairs:
            cid = chunk.metadata.chunk_id
            if cid in self._id_to_row:
                logger.debug("Duplicate chunk skipped in vector store", chunk_id=cid)
                continue
            vectors_to_add.append(vector)
            meta = chunk.metadata.to_dict()
            meta["text"] = chunk.text
            metas_to_add.append(meta)

        if not vectors_to_add:
            return 0

        arr = np.array(vectors_to_add, dtype=np.float32)
        faiss.normalize_L2(arr)

        start_row = self._index.ntotal
        self._index.add(arr)

        for offset, meta in enumerate(metas_to_add):
            row = start_row + offset
            self._metadata.append(meta)
            self._id_to_row[meta["chunk_id"]] = row

        logger.info("Vectors added to FAISS", added=len(vectors_to_add), total=self._index.ntotal)
        return len(vectors_to_add)

    def search(self, query_vector: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        if self._index.ntotal == 0:
            logger.warning("Search on empty index")
            return []

        q = np.array([query_vector], dtype=np.float32)
        faiss.normalize_L2(q)
        scores, indices = self._index.search(q, min(top_k, self._index.ntotal))

        results: List[Dict[str, Any]] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            entry = dict(self._metadata[idx])
            entry["score"] = float(score)
            results.append(entry)

        logger.info("FAISS search complete", top_k=top_k, returned=len(results))
        return results

    def delete_by_chunk_ids(self, chunk_ids: List[str]) -> int:
        to_remove = set(chunk_ids) & set(self._id_to_row.keys())
        if not to_remove:
            return 0

        keep_rows = [i for i, meta in enumerate(self._metadata) if meta["chunk_id"] not in to_remove]

        if keep_rows:
            vectors = np.array([self._index.reconstruct(int(i)) for i in keep_rows], dtype=np.float32)
        else:
            vectors = np.empty((0, self.dimension), dtype=np.float32)

        kept_meta = [self._metadata[i] for i in keep_rows]

        self._index.reset()
        self._metadata.clear()
        self._id_to_row.clear()

        if vectors.shape[0] > 0:
            self._index.add(vectors)
            for row, meta in enumerate(kept_meta):
                self._metadata.append(meta)
                self._id_to_row[meta["chunk_id"]] = row

        removed = len(to_remove)
        logger.info("Chunks deleted from FAISS", removed=removed, remaining=self._index.ntotal)
        return removed

    def save(self) -> None:
        _STORE_DIR.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(_INDEX_FILE))
        with open(_META_FILE, "w", encoding="utf-8") as f:
            json.dump(self._metadata, f, ensure_ascii=False, indent=2)
        logger.info("Vector store saved", index_path=str(_INDEX_FILE), vectors=self._index.ntotal)

    def _load(self) -> None:
        try:
            self._index = faiss.read_index(str(_INDEX_FILE))
            with open(_META_FILE, "r", encoding="utf-8") as f:
                self._metadata = json.load(f)
            self._id_to_row = {meta["chunk_id"]: i for i, meta in enumerate(self._metadata)}
            logger.info("Vector store loaded from disk", vectors=self._index.ntotal)
        except Exception as exc:
            logger.error("Failed to load vector store", error=str(exc))
            self._index = faiss.IndexFlatIP(self.dimension)
            self._metadata = []
            self._id_to_row = {}

    @property
    def size(self) -> int:
        return self._index.ntotal

    def clear(self) -> None:
        self._index.reset()
        self._metadata.clear()
        self._id_to_row.clear()
        logger.info("Vector store cleared")


# ---------------------------------------------------------------------------
# Module‑level singleton
# ---------------------------------------------------------------------------
# Type hinted as BaseVectorStore to enforce abstraction
vector_store: BaseVectorStore = FAISSVectorStore(dimension=settings.embedding_dimension)
