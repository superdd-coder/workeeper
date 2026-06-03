from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.db.qdrant import QdrantManager
from src.providers.base import EmbeddingProvider

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    text: str
    score: float
    metadata: dict = field(default_factory=dict)


class Retriever:
    def __init__(self, db: QdrantManager, embedding: EmbeddingProvider):
        self.db = db
        self.embedding = embedding
        self._sparse_encoder = None

    def _get_sparse_encoder(self):
        if self._sparse_encoder is None:
            from src.rag.sparse_encoder import SparseEncoder
            self._sparse_encoder = SparseEncoder()
        return self._sparse_encoder

    def retrieve(
        self,
        query: str,
        collection: str = "default",
        top_k: int = 10,
        embedding_override: EmbeddingProvider | None = None,
        search_mode: str = "dense",
        min_score: float = 0.0,
    ) -> list[RetrievedChunk]:
        emb = embedding_override or self.embedding
        query_vector = emb.embed_query(query)
        logger.info("Retriever.retrieve: collection=%s, search_mode=%s, vector_dim=%d, top_k=%d, min_score=%.2f",
                     collection, search_mode, len(query_vector), top_k, min_score)

        if search_mode == "hybrid":
            chunks = self._hybrid_retrieve(query, query_vector, collection, top_k)
        else:
            results = self.db.search(
                collection=collection, query_vector=query_vector, top_k=top_k
            )
            chunks = self._to_chunks(results)

        logger.info("Retriever.retrieve: collection=%s, got %d results", collection, len(chunks))
        # Threshold only applies to dense mode (cosine scores 0-1), not hybrid (RRF rank scores)
        if min_score > 0 and search_mode != "hybrid":
            chunks = [c for c in chunks if c.score >= min_score]
        return chunks

    def _hybrid_retrieve(
        self, query: str, query_vector: list[float], collection: str, top_k: int
    ) -> list[RetrievedChunk]:
        """Hybrid dense + sparse search. Falls back to dense on failure."""
        try:
            encoder = self._get_sparse_encoder()
            # Build vocab from sample documents
            sample_results = self.db.search(
                collection=collection, query_vector=query_vector, top_k=100
            )
            sample_texts = [r["payload"].get("text", "") for r in sample_results]
            if sample_texts:
                encoder.build_vocab(sample_texts)
            sparse_vector = encoder.encode_query(query) if sample_texts else None

            results = self.db.hybrid_search(
                collection=collection,
                query_vector=query_vector,
                sparse_vector=sparse_vector,
                top_k=top_k,
            )
            return self._to_chunks(results)
        except Exception:
            # Fallback to dense
            results = self.db.search(
                collection=collection, query_vector=query_vector, top_k=top_k
            )
            return self._to_chunks(results)

    @staticmethod
    def _to_chunks(results: list[dict]) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(
                text=r["payload"].get("text", ""),
                score=r["score"],
                metadata={k: v for k, v in r["payload"].items() if k != "text"} | {"id": r["id"]},
            )
            for r in results
        ]


def multi_collection_retrieve(
    retriever: Retriever,
    query: str,
    collections: list[str],
    top_k: int = 10,
    reranker=None,
    embedding_overrides: dict[str, EmbeddingProvider] | None = None,
    search_mode: str = "dense",
    min_score: float = 0.0,
) -> list[RetrievedChunk]:
    """Search across multiple collections with optional cross-collection reranking."""
    logger.info("multi_collection_retrieve: collections=%s, top_k=%d, search_mode=%s, has_overrides=%s",
                collections, top_k, search_mode, bool(embedding_overrides))
    all_results: list[RetrievedChunk] = []
    seen_texts: set[str] = set()

    for col in collections:
        override = embedding_overrides.get(col) if embedding_overrides else None
        logger.info("multi_collection_retrieve: searching col=%s, has_override=%s", col, override is not None)
        try:
            chunks = retriever.retrieve(
                query, collection=col, top_k=top_k,
                embedding_override=override, search_mode=search_mode, min_score=min_score,
            )
            logger.info("multi_collection_retrieve: col=%s returned %d chunks", col, len(chunks))
        except Exception as e:
            logger.error("multi_collection_retrieve: col=%s failed: %s", col, e)
            chunks = []
        for c in chunks:
            if c.text not in seen_texts:
                seen_texts.add(c.text)
                c.metadata["collection"] = col
                all_results.append(c)

    logger.info("multi_collection_retrieve: total %d results from %d collections", len(all_results), len(collections))
    if reranker and all_results:
        all_results = reranker.rerank(query, all_results)

    # Sort by score descending so best results across all collections survive the top_k cut
    all_results.sort(key=lambda c: c.score, reverse=True)
    return all_results[:top_k]
