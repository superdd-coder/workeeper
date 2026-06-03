from __future__ import annotations

import logging

from fastapi import APIRouter

from src.api.schemas import (
    CollectionCreateRequest,
    CollectionConfigUpdateRequest,
    CollectionInfo,
)
from src.services import services

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/collections")
def list_collections():
    names = [c for c in services.db.list_collections() if c != "__summaries__"]
    result = []
    for name in names:
        try:
            info = services.db.get_collection_info(name)
            result.append({"name": name, "points_count": info.get("points_count", 0)})
        except Exception:
            result.append({"name": name, "points_count": 0})
    return result


@router.post("/collections")
def create_collection(req: CollectionCreateRequest):
    if services.db.collection_exists(req.name):
        return {"error": f"Collection '{req.name}' already exists"}
    logger.info("Creating collection: %s (dimensions=%s, mode=%s)", req.name, req.dimensions, req.chunk_mode)
    if not services.embedding:
        return {"error": "Embedding provider not configured. Please configure it in Settings first."}
    dimensions = req.dimensions or services.embedding.dimensions
    chunk_config = {
        "chunk_mode": req.chunk_mode,
        "parent_strategy": req.parent_strategy,
        "chunk_size": req.chunk_size,
        "chunk_overlap": req.chunk_overlap,
        "buffer_ratio": req.buffer_ratio,
        "parent_chunk_size": req.parent_chunk_size,
        "parent_chunk_overlap": req.parent_chunk_overlap,
        "child_chunk_size": req.child_chunk_size,
        "child_chunk_overlap": req.child_chunk_overlap,
        "search_mode": req.search_mode,
        "contextual_enabled": req.contextual_enabled,
        "contextual_window": req.contextual_window,
        "agent_enabled": req.agent_enabled,
        "agent_max_iterations": req.agent_max_iterations,
        "rerank_top_k": req.rerank_top_k,
    }
    # Only include embedding/rerank overrides if provided
    if req.embedding_provider is not None:
        chunk_config["embedding_provider"] = req.embedding_provider
    if req.embedding_model is not None:
        chunk_config["embedding_model"] = req.embedding_model
    if req.embedding_base_url is not None:
        chunk_config["embedding_base_url"] = req.embedding_base_url
    if req.embedding_api_key is not None:
        chunk_config["embedding_api_key"] = req.embedding_api_key
    if req.embedding_batch_size is not None:
        chunk_config["embedding_batch_size"] = req.embedding_batch_size
    if req.rerank_provider is not None:
        chunk_config["rerank_provider"] = req.rerank_provider
    if req.rerank_model is not None:
        chunk_config["rerank_model"] = req.rerank_model
    if req.rerank_base_url is not None:
        chunk_config["rerank_base_url"] = req.rerank_base_url
    if req.rerank_api_key is not None:
        chunk_config["rerank_api_key"] = req.rerank_api_key
    if req.allowed_file_types is not None:
        chunk_config["allowed_file_types"] = req.allowed_file_types

    services.db.create_collection(req.name, vector_size=dimensions, chunk_config=chunk_config)
    return {"message": f"Collection '{req.name}' created", "dimensions": dimensions}


@router.delete("/collections/{name}")
def delete_collection(name: str):
    if not services.db.collection_exists(name):
        return {"error": f"Collection '{name}' does not exist"}
    collections = [c for c in services.db.list_collections() if c != "__summaries__"]
    if len(collections) <= 1:
        return {"error": "Cannot delete the only remaining collection"}
    services.db.delete_collection(name)
    logger.info("Deleted collection: %s", name)
    return {"message": f"Collection '{name}' deleted"}


@router.get("/collections/{name}/info", response_model=CollectionInfo)
def collection_info(name: str):
    info = services.db.get_collection_info(name)
    return CollectionInfo(**info)


@router.get("/collections/{name}/config")
def get_collection_config(name: str):
    if not services.db.collection_exists(name):
        return {"error": f"Collection '{name}' does not exist"}
    config = services.db.get_collection_config(name)
    return config


@router.put("/collections/{name}/config")
def update_collection_config(name: str, req: CollectionConfigUpdateRequest):
    if not services.db.collection_exists(name):
        return {"error": f"Collection '{name}' does not exist"}

    # Filter out None values (only update provided fields)
    updates = {k: v for k, v in req.model_dump().items() if v is not None}

    if not updates:
        return {"message": "No changes provided"}

    result = services.db.update_collection_config(name, updates)
    if "error" in result:
        return result

    return {"message": f"Collection '{name}' config updated", "config": result}
