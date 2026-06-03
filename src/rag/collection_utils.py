"""Shared utilities for per-collection embedding, parent-child retrieval, and context building."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

from src.config import EmbeddingProviderConfig
from src.providers.base import EmbeddingProvider, RerankerProvider
from src.providers.embedding import create_embedding_provider
from src.providers.reranker import create_reranker_provider
from src.rag.retriever import RetrievedChunk


def _find_provider_by_id(providers: list, provider_id: str):
    """Find a provider config by ID from a list."""
    return next((p for p in providers if p.id == provider_id), None)


def get_collection_embedding(col_config: dict, collection: str = "") -> EmbeddingProvider | None:
    """Create an embedding provider for a specific collection, falling back to global."""
    from src.services import services

    actual_dim = services.db.get_vector_size(collection) if collection else None

    # 1. Check for per-collection provider ID reference
    provider_id = col_config.get("embedding_provider_id")
    if provider_id:
        provider_cfg = _find_provider_by_id(services.config.embedding.providers, provider_id)
        if provider_cfg:
            cfg = provider_cfg.model_copy()
            if actual_dim:
                cfg.dimensions = actual_dim
            return create_embedding_provider(cfg)

    # 2. Check for old-style per-collection override fields (backward compat)
    old_provider = col_config.get("embedding_provider")
    if old_provider and old_provider != "none":
        global_default = services.config.embedding.default
        # Check if we have valid credentials for this override
        has_credentials = bool(
            col_config.get("embedding_api_key")
            or (global_default and global_default.api_key)
        )
        # Only use old-style override if we have credentials or it's a local provider
        if has_credentials or old_provider == "local":
            dim = actual_dim or col_config.get("dimensions") or (global_default.dimensions if global_default else 512)
            cfg = EmbeddingProviderConfig(
                provider=old_provider,
                model=col_config.get("embedding_model") or (global_default.model if global_default else ""),
                base_url=col_config.get("embedding_base_url") or (global_default.base_url if global_default else ""),
                api_key=col_config.get("embedding_api_key") or (global_default.api_key if global_default else ""),
                dimensions=dim,
                batch_size=col_config.get("embedding_batch_size") or (global_default.batch_size if global_default else 10),
            )
            return create_embedding_provider(cfg)

    # 3. Fall back to global default
    global_default = services.config.embedding.default
    if global_default:
        cfg = global_default.model_copy()
        if actual_dim:
            cfg.dimensions = actual_dim
        return create_embedding_provider(cfg)

    return None


def get_collection_reranker(col_config: dict) -> RerankerProvider | None:
    """Create a reranker provider for a specific collection, falling back to global."""
    from src.services import services

    # 1. Check for per-collection provider ID reference
    provider_id = col_config.get("rerank_provider_id")
    if provider_id:
        provider_cfg = _find_provider_by_id(services.config.rerank.providers, provider_id)
        if provider_cfg:
            return create_reranker_provider(provider_cfg)

    # 2. Fall back to global default
    global_default = services.config.rerank.default
    if global_default:
        return create_reranker_provider(global_default)

    return None


def get_embedding_overrides(collections: list[str]) -> dict[str, EmbeddingProvider]:
    """Build per-collection embedding providers for a list of collections."""
    from src.services import services

    overrides = {}
    for col in collections:
        cc = services.db.get_collection_config(col)
        overrides[col] = get_collection_embedding(cc, col)
    return overrides


def retrieve_parent_child(
    query: str,
    collection: str,
    top_k: int,
    embedding: EmbeddingProvider | None = None,
    db=None,
    min_score: float = 0.0,
) -> tuple[list[RetrievedChunk], list[dict]]:
    """Search child chunks, return parent chunks with best child scores.

    Returns:
        (parent_chunks, child_groups) where child_groups maps parent_id -> child data
    """
    from qdrant_client.models import FieldCondition, Filter, MatchValue
    from src.services import services

    _db = db or services.db
    emb = embedding or services.embedding

    query_vector = emb.embed_query(query)
    child_filter = Filter(
        must=[FieldCondition(key="chunk_type", match=MatchValue(value="child"))]
    )
    # Search many children so we can find enough unique parents.
    # top_k controls the final parent count, not the child count.
    top_k = int(top_k) if top_k else 10
    child_search_limit = max(top_k * 10, 50)
    child_results = _db.search(
        collection=collection,
        query_vector=query_vector,
        top_k=child_search_limit,
        filter_condition=child_filter,
    )

    if min_score > 0:
        child_results = [r for r in child_results if r["score"] >= min_score]

    if not child_results:
        return [], []

    # Collect unique parent IDs
    parent_ids = list({
        r["payload"]["parent_id"]
        for r in child_results
        if r["payload"].get("parent_id")
    })

    if not parent_ids:
        # No parent IDs — return child results as-is
        chunks = [RetrievedChunk(
            text=r["payload"].get("text", ""),
            score=r["score"],
            metadata={k: v for k, v in r["payload"].items() if k != "text"},
        ) for r in child_results]
        return chunks, []

    # Retrieve parent chunks
    parent_points = _db.get_points_by_ids(collection, parent_ids)
    parent_map = {p["id"]: p["payload"] for p in parent_points}

    # Group children by parent and build parent results
    child_groups: dict[str, list[dict]] = {}
    seen_parents: dict[str, RetrievedChunk] = {}

    for r in child_results:
        pid = r["payload"].get("parent_id")
        if not pid:
            continue

        # Track children
        if pid not in child_groups:
            child_groups[pid] = []
        child_groups[pid].append({
            "id": str(r["id"]),
            "text": r["payload"].get("text", ""),
            "score": r["score"],
            "source": r["payload"].get("source", ""),
            "collection": collection,
            "chunk_index": r["payload"].get("chunk_index", 0),
            "chunk_type": "child",
            "context": r["payload"].get("context"),
            "parent_id": pid,
        })

        # Best parent result per parent_id
        if pid not in seen_parents or r["score"] > seen_parents[pid].score:
            parent_payload = parent_map.get(pid, r["payload"])
            seen_parents[pid] = RetrievedChunk(
                text=parent_payload.get("text", ""),
                score=r["score"],
                metadata={k: v for k, v in parent_payload.items() if k != "text"} | {"id": pid},
            )

    results = sorted(seen_parents.values(), key=lambda c: c.score, reverse=True)
    groups = [{"parent_id": pid, "children": children} for pid, children in child_groups.items()]
    return results[:top_k], groups


def build_context(chunks: list) -> str:
    """Build context string from chunks, prepending summary and context metadata.

    Accepts either RetrievedChunk objects or dicts with 'text' and 'metadata' keys.
    """
    parts = []
    for c in chunks:
        if hasattr(c, "text"):
            text = c.text
            meta = c.metadata if hasattr(c, "metadata") else {}
        elif isinstance(c, dict):
            text = c.get("text", "")
            meta = c.get("metadata", {})
        else:
            continue

        ctx = meta.get("context", "")
        summ = meta.get("summary", "")
        if summ:
            text = f"[Document: {summ}]\n{text}"
        if ctx:
            text = f"[Context: {ctx}]\n{text}"
        parts.append(text)

    return "\n\n".join(parts)
