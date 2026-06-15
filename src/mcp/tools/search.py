from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def rag_query(
    question: str,
    collection: str = "default",
    collections: list[str] | None = None,
    use_agent: bool = True,
    search_mode: str = "dense",
    top_k: int = 5,
    rerank_top_k: int = 5,
    use_reranker: bool = True,
    max_iterations: int = 3,
    min_score: float = 0.0,
    temperature: float | None = None,
) -> str:
    """Ask a question and get an AI-generated answer with source citations from the knowledge base.

    This is the primary query tool. Uses Agentic RAG by default (iterative retrieval with LLM grading and rewriting)
    for higher quality answers. Set use_agent=false for faster single-pass retrieval.

    For raw search results without LLM generation, use `search_chunks` instead.
    """
    from src.services import services
    from src.rag.agent import AgenticRAG, AgentResult
    from src.rag.collection_utils import build_context, get_embedding_overrides, retrieve_parent_child
    from src.rag.retriever import multi_collection_retrieve

    def _run():
        target_collections = collections or [collection]

        if not services.db.collection_exists(collection):
            return {"error": f"Collection '{collection}' does not exist"}

        col_config = services.db.get_collection_config(collection)
        embedding_overrides = get_embedding_overrides(target_collections)
        col_embedding = embedding_overrides.get(collection) or next(iter(embedding_overrides.values()), None)

        reranker = services.reranker if (use_reranker and services.reranker and services.reranker.provider) else None
        is_parent_child = col_config.get("chunk_mode") == "parent_child"

        llm = services.llm
        if llm is None:
            return {"error": "LLM provider not configured"}

        if is_parent_child and not use_agent:
            results = []
            for col in target_collections:
                chunks, _ = retrieve_parent_child(
                    question, col, top_k, embedding=embedding_overrides.get(col), min_score=min_score,
                )
                for c in chunks:
                    c.metadata["collection"] = col
                results.extend(chunks)
            seen: set[str] = set()
            unique = [r for r in results if r.text not in seen and not seen.add(r.text)]
            results = sorted(unique, key=lambda x: x.score, reverse=True)[:top_k]
            if reranker and results:
                results = reranker.rerank(question, results)
            context = build_context(results)
            sources = [{"text": c.text, "score": c.score, "metadata": c.metadata} for c in results]
            answer = llm.generate(f"Answer based on context:\n{context}\n\nQuestion: {question}", temperature=temperature)
            return {"answer": answer, "sources": sources, "iterations": 1, "query_used": question}

        elif use_agent:
            agent = AgenticRAG(
                llm=llm, retriever=services.retriever, reranker=reranker,
                rerank_top_k=rerank_top_k, max_iterations=max_iterations,
                embedding_overrides=embedding_overrides, search_mode=search_mode,
                min_score=min_score, db=services.db, temperature=temperature,
            )
            result = agent.run(query=question, collections=target_collections, top_k=top_k)
            return {"answer": result.answer, "sources": result.sources, "iterations": result.iterations, "query_used": result.query_used}

        else:
            if len(target_collections) > 1:
                chunks = multi_collection_retrieve(
                    services.retriever, question, target_collections,
                    top_k=top_k, embedding_overrides=embedding_overrides,
                    search_mode=search_mode, min_score=min_score,
                )
            else:
                chunks = services.retriever.retrieve(
                    query=question, collection=collection, top_k=top_k,
                    embedding_override=col_embedding, search_mode=search_mode, min_score=min_score,
                )
            if reranker and chunks:
                chunks = reranker.rerank(question, chunks)
            context = build_context(chunks)
            sources = [{"text": c.text, "score": c.score, "metadata": c.metadata} for c in chunks]
            answer = llm.generate(f"Answer based on context:\n{context}\n\nQuestion: {question}", temperature=temperature)
            return {"answer": answer, "sources": sources, "iterations": 1, "query_used": question}

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _run)
    if "error" in result:
        return json.dumps(result, ensure_ascii=False)
    result["sources"] = result["sources"][:5]
    return json.dumps(result, ensure_ascii=False, default=str)


async def search_chunks(
    query: str,
    collections: list[str] | None = None,
    search_mode: str = "dense",
    top_k: int = 10,
    rerank_top_k: int = 5,
    use_reranker: bool = False,
    use_agent: bool = False,
    min_score: float = 0.0,
) -> str:
    """Search for relevant document chunks without LLM generation. Returns raw chunks with relevance scores.

    Use this when you need to inspect what the retriever finds (debugging retrieval quality) or when you want
    to retrieve context for your own processing. For an AI-generated answer, use `rag_query` instead.
    """
    from src.services import services
    from src.rag.agent import AgenticRAG
    from src.rag.collection_utils import get_embedding_overrides
    from src.rag.retriever import multi_collection_retrieve

    target_collections = collections or ["default"]

    def _run():
        embedding_overrides = get_embedding_overrides(target_collections)
        reranker = services.reranker if (use_reranker and services.reranker and services.reranker.provider) else None

        if use_agent:
            if services.llm is None:
                return {"error": "LLM provider not configured for agentic search"}
            agent = AgenticRAG(
                llm=services.llm, retriever=services.retriever, reranker=reranker,
                rerank_top_k=rerank_top_k, embedding_overrides=embedding_overrides,
                search_mode=search_mode, min_score=min_score, db=services.db,
            )
            result = agent.run(query=query, collections=target_collections, top_k=top_k)
            return {
                "results": [{"text": s["text"], "score": s["score"], "source": s.get("metadata", {}).get("source", ""), "collection": s.get("metadata", {}).get("collection", "")} for s in result.sources],
                "query_used": result.query_used,
                "agent_iterations": result.iterations,
            }

        chunks = multi_collection_retrieve(
            services.retriever, query, target_collections,
            top_k=top_k, embedding_overrides=embedding_overrides,
            search_mode=search_mode, min_score=min_score,
        )
        if reranker and chunks:
            chunks = reranker.rerank(query, chunks)

        return {
            "results": [
                {"text": c.text, "score": c.score, "source": c.metadata.get("source", ""), "collection": c.metadata.get("collection", ""), "chunk_type": c.metadata.get("chunk_type", "normal"), "context": c.metadata.get("context")}
                for c in chunks
            ],
            "query_used": query,
            "agent_iterations": 0,
        }

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _run)
    return json.dumps(result, ensure_ascii=False, default=str)


async def get_query_history(limit: int = 50) -> str:
    """Get recent questions, answers, and sources from past RAG queries.

    Useful for reviewing what has been asked before or referencing previous answers.
    """
    def _run():
        file = Path("data/history/history.jsonl")
        if not file.exists():
            return []
        entries = []
        for line in file.read_text().strip().split("\n"):
            if line:
                entries.append(json.loads(line))
        return entries[-limit:]

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _run)
    return json.dumps(result, ensure_ascii=False, default=str)
