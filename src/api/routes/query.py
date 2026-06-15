from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from src.api.schemas import QueryRequest, QueryResponse, SourceItem
from src.config import get_config
from src.rag.agent import AgenticRAG, AgentResult
from src.services import services
from src.rag.collection_utils import (
    build_context,
    get_embedding_overrides,
    retrieve_parent_child_multi,
    retrieve_standard,
)
from src.rag.agent import AgenticRAG, AgentResult

logger = logging.getLogger(__name__)
router = APIRouter()

HISTORY_DIR = Path("data/history")
HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def _save_history(question: str, answer: str, collection: str, sources: list):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "question": question,
        "answer": answer,
        "collection": collection,
        "sources": sources,
    }
    file = HISTORY_DIR / "history.jsonl"
    with open(file, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _resolve_params(req: QueryRequest, col_config: dict) -> dict:
    """Resolve all query parameters from request + collection config + global config."""
    agent_enabled = req.use_agent and col_config.get("agent_enabled", col_config.get("self_rag_enabled", True))
    # Agentic RAG requires reranker — force enable when agent is on
    use_reranker = req.use_reranker if req.use_reranker is not None else True
    if agent_enabled:
        use_reranker = True
    return {
        "top_k": req.top_k or col_config.get("top_k", services.config.rag.top_k),
        "rerank_top_k": req.rerank_top_k or col_config.get("rerank_top_k", services.config.rag.rerank_top_k),
        "agent_enabled": agent_enabled,
        "search_mode": req.search_mode or col_config.get("search_mode", "dense"),
        "min_score": req.min_score if req.min_score is not None else 0.0,
        "use_reranker": use_reranker,
        "max_iterations": req.max_iterations if req.max_iterations is not None else col_config.get("agent_max_iterations", col_config.get("self_rag_max_iterations", 3)),
    }


def _resolve_llm(req: QueryRequest) -> tuple:
    """Resolve LLM and provider info for streaming (supports per-request provider switching)."""
    from src.providers.llm import create_llm_for_provider

    provider_info = {"name": "", "model": ""}
    config = get_config()

    if req.provider_id:
        for p in config.llm.providers:
            if p.id == req.provider_id:
                llm = create_llm_for_provider(p, model=req.model)
                provider_info["name"] = p.name
                provider_info["model"] = req.model or p.default_model or p.model
                return llm, provider_info, req.temperature

    if config.llm.providers:
        default_p = next((p for p in config.llm.providers if p.is_default), config.llm.providers[0])
        llm = create_llm_for_provider(default_p)
        provider_info["name"] = default_p.name
        provider_info["model"] = default_p.default_model or default_p.model
        return llm, provider_info, req.temperature

    return services.llm, provider_info, req.temperature


@router.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    try:
        if not services.db.collection_exists(req.collection):
            return QueryResponse(
                answer=f"Collection '{req.collection}' does not exist. Please create it first.",
                sources=[], iterations=0, query_used=req.question,
            )

        col_config = services.db.get_collection_config(req.collection)
        params = _resolve_params(req, col_config)
        llm, provider_info, temperature = _resolve_llm(req)
        target_collections = req.collections or [req.collection]
        embedding_overrides = get_embedding_overrides(target_collections)
        col_embedding = embedding_overrides.get(req.collection) or next(iter(embedding_overrides.values()))

        logger.info("Query: collections=%s, min_score=%.2f, search_mode=%s",
                     target_collections, params["min_score"], params["search_mode"])

        is_parent_child = col_config.get("chunk_mode") == "parent_child"
        reranker = services.reranker if (params["use_reranker"] and services.reranker and services.reranker.provider) else None

        if is_parent_child and not params["agent_enabled"]:
            chunks = retrieve_parent_child_multi(
                req.question, target_collections, params["top_k"],
                embedding_overrides=embedding_overrides,
                min_score=params["min_score"],
                reranker=reranker,
                rerank_top_k=params["rerank_top_k"],
            )
            context = build_context(chunks)
            sources = [{"text": c.text, "score": c.score, "metadata": c.metadata} for c in chunks]
            answer = llm.generate(f"Answer based on context:\n{context}\n\nQuestion: {req.question}", temperature=temperature)
            result = AgentResult(answer=answer, sources=sources, iterations=1, query_used=req.question)
        elif params["agent_enabled"]:
            agent = AgenticRAG(
                llm=llm,
                retriever=services.retriever,
                reranker=reranker,
                rerank_top_k=params["rerank_top_k"],
                max_iterations=params["max_iterations"],
                embedding_overrides=embedding_overrides,
                search_mode=params["search_mode"],
                min_score=params["min_score"],
                db=services.db,
                temperature=temperature,
            )
            result = agent.run(query=req.question, collections=target_collections, top_k=params["top_k"])
        else:
            chunks = retrieve_standard(
                req.question, target_collections, params["top_k"],
                embedding_overrides=embedding_overrides,
                search_mode=params["search_mode"],
                min_score=params["min_score"],
                reranker=reranker,
                rerank_top_k=params["rerank_top_k"],
            )
            context = build_context(chunks)
            sources = [{"text": c.text, "score": c.score, "metadata": c.metadata} for c in chunks]
            answer = llm.generate(f"Answer based on context:\n{context}\n\nQuestion: {req.question}", temperature=temperature)
            result = AgentResult(answer=answer, sources=sources, iterations=1, query_used=req.question)

        sources = [SourceItem(**s) for s in result.sources]
        _save_history(req.question, result.answer, req.collection, result.sources)
        return QueryResponse(
            answer=result.answer, sources=sources,
            iterations=result.iterations, query_used=result.query_used,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error processing query: {str(e)}")


@router.post("/query/stream")
async def query_stream(req: QueryRequest):
    """SSE streaming endpoint — streams answer tokens one by one."""

    def generate():
        try:
            if not services.db.collection_exists(req.collection):
                yield f"data: {json.dumps({'type': 'error', 'content': f'Collection {req.collection} does not exist'})}\n\n"
                return

            col_config = services.db.get_collection_config(req.collection)
            params = _resolve_params(req, col_config)
            llm, provider_info, temperature = _resolve_llm(req)
            target_collections = req.collections or [req.collection]
            embedding_overrides = get_embedding_overrides(target_collections)
            col_embedding = embedding_overrides.get(req.collection) or next(iter(embedding_overrides.values()))

            logger.info("Query stream: collections=%s, min_score=%.2f, search_mode=%s",
                         target_collections, params["min_score"], params["search_mode"])

            is_parent_child = col_config.get("chunk_mode") == "parent_child"
            reranker = services.reranker if (params["use_reranker"] and services.reranker and services.reranker.provider) else None

            if is_parent_child and not params["agent_enabled"]:
                chunks = retrieve_parent_child_multi(
                    req.question, target_collections, params["top_k"],
                    embedding_overrides=embedding_overrides,
                    min_score=params["min_score"],
                    reranker=reranker,
                    rerank_top_k=params["rerank_top_k"],
                )
                context = build_context(chunks)
                sources = [{"text": c.text, "score": c.score, "metadata": c.metadata} for c in chunks]
                meta = {
                    "type": "meta", "sources": sources, "iterations": 1,
                    "query_used": req.question, "mode": "parent-child", "agent_active": False,
                    "provider": provider_info["name"], "model": provider_info["model"],
                    "search_mode": params["search_mode"],
                }
                yield f"data: {json.dumps(meta)}\n\n"
                answer_parts = []
                for token in llm.generate_stream(f"Answer based on context:\n{context}\n\nQuestion: {req.question}", temperature=temperature):
                    answer_parts.append(token)
                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                _save_history(req.question, "".join(answer_parts), req.collection, sources)

            elif params["agent_enabled"]:
                agent = AgenticRAG(
                    llm=llm, retriever=services.retriever,
                    reranker=reranker,
                    rerank_top_k=params["rerank_top_k"],
                    max_iterations=params["max_iterations"],
                    embedding_overrides=embedding_overrides,
                    search_mode=params["search_mode"],
                    min_score=params["min_score"],
                    db=services.db,
                    temperature=temperature,
                )
                gen = agent.run_stream(query=req.question, collections=target_collections, top_k=params["top_k"])
                for first, second in gen:
                    if isinstance(first, dict):
                        yield f"data: {json.dumps(first)}\n\n"
                        continue
                    result = first
                    stream = second
                    meta = {
                        "type": "meta", "sources": result.sources, "iterations": result.iterations,
                        "query_used": result.query_used, "mode": "agentic", "agent_active": True,
                        "provider": provider_info["name"], "model": provider_info["model"],
                        "search_mode": params["search_mode"],
                    }
                    yield f"data: {json.dumps(meta)}\n\n"
                    if result.answer:
                        yield f"data: {json.dumps({'type': 'token', 'content': result.answer})}\n\n"
                        _save_history(req.question, result.answer, req.collection, result.sources)
                    else:
                        answer_parts = []
                        for token in stream:
                            answer_parts.append(token)
                            yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                        _save_history(req.question, "".join(answer_parts), req.collection, result.sources)

            else:
                chunks = retrieve_standard(
                    req.question, target_collections, params["top_k"],
                    embedding_overrides=embedding_overrides,
                    search_mode=params["search_mode"],
                    min_score=params["min_score"],
                    reranker=reranker,
                    rerank_top_k=params["rerank_top_k"],
                )
                context = build_context(chunks)
                sources = [{"text": c.text, "score": c.score, "metadata": c.metadata} for c in chunks]
                meta = {
                    "type": "meta", "sources": sources, "iterations": 1,
                    "query_used": req.question, "mode": "standard", "agent_active": False,
                    "provider": provider_info["name"], "model": provider_info["model"],
                    "search_mode": params["search_mode"],
                }
                yield f"data: {json.dumps(meta)}\n\n"
                answer_parts = []
                for token in llm.generate_stream(f"Answer based on context:\n{context}\n\nQuestion: {req.question}", temperature=temperature):
                    answer_parts.append(token)
                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                _save_history(req.question, "".join(answer_parts), req.collection, sources)

            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/history")
def get_history(limit: int = 50):
    file = HISTORY_DIR / "history.jsonl"
    if not file.exists():
        return []
    entries = []
    for line in file.read_text().strip().split("\n"):
        if line:
            entries.append(json.loads(line))
    return entries[-limit:]
