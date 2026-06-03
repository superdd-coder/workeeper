"""Agentic RAG — iterative retrieval with LLM-guided grading, decomposition, and rewriting.

Pipeline: Retrieve -> Grade -> Decompose/Rewrite -> Rerank -> Synthesize
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from src.providers.base import EmbeddingProvider, LLMProvider
from src.rag.retriever import RetrievedChunk, Retriever
from src.rag.collection_utils import retrieve_parent_child, build_context

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    answer: str
    sources: list[dict] = field(default_factory=list)
    iterations: int = 0
    query_used: str = ""


# ── Prompts (system + user separation for prefix caching) ────────

GRADE_SYSTEM = (
    "Determine if the search results contain enough information to answer the query. "
    "Results are only sufficient if they directly answer the question, not just relate to the topic. "
    'Respond with JSON: {"sufficient": true} if the query can be answered from the results, {"sufficient": false} otherwise.'
)
GRADE_USER = "Query: {query}\nTop results:\n{top_chunks}"

DECOMPOSE_SYSTEM = (
    "Break a complex query into 2-3 focused sub-questions that together cover the original query. "
    'Respond with a JSON array of strings: ["sub-question 1", "sub-question 2", ...]'
)
DECOMPOSE_USER = "Query: {query}"

REWRITE_SYSTEM = (
    "Rewrite the query to be more specific and searchable. "
    "Respond with ONLY the rewritten query, nothing else."
)
REWRITE_USER = "Query that returned no relevant results: {query}"

GENERATE_SYSTEM = (
    "Answer the question based on the provided context. "
    "If the context doesn't contain enough information, say so."
)
GENERATE_USER = "Context:\n{context}\n\nQuestion: {question}"


def _parse_json(text: str):
    """Parse JSON from LLM output, handling markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines)
    return json.loads(text)


class AgenticRAG:
    def __init__(
        self,
        llm: LLMProvider,
        retriever: Retriever,
        reranker=None,
        rerank_top_k: int | None = None,
        max_iterations: int = 3,
        on_step: Callable[[str, str], None] | None = None,
        embedding_overrides: dict[str, EmbeddingProvider] | None = None,
        search_mode: str = "dense",
        min_score: float = 0.0,
        db=None,
        temperature: float | None = None,
    ):
        self.llm = llm
        self.retriever = retriever
        self.reranker = reranker
        self.rerank_top_k = rerank_top_k
        self.max_iterations = max_iterations
        self.on_step = on_step or (lambda step, content: None)
        self.embedding_overrides = embedding_overrides or {}
        self.search_mode = search_mode
        self.min_score = min_score
        self.db = db
        self.temperature = temperature

    # ── Public API ───────────────────────────────────────────────

    def _run_retrieval(
        self,
        query: str,
        collections: list[str],
        top_k: int,
        max_iter: int,
        rerank_top_k: int | None = None,
    ):
        """Generator that yields step event dicts, then yields (chunks, current_query) as final result."""
        all_chunks: list[RetrievedChunk] = []
        current_query = query
        result_top_k = rerank_top_k if rerank_top_k is not None else top_k

        for iteration in range(max_iter):
            yield {"type": "step", "step": "retrieving", "content": f"Iteration {iteration + 1}/{max_iter}: Searching {len(collections)} collection(s)..."}
            logger.info("[AgenticRAG] Iteration %d/%d: query='%s', collections=%s",
                        iteration + 1, max_iter, current_query[:50], collections)
            chunks = self._retrieve(current_query, collections, top_k)
            if not chunks:
                yield {"type": "step", "step": "rewriting", "content": "No results found, rewriting query..."}
                logger.info("[AgenticRAG] No chunks found, rewriting query")
                current_query = self._rewrite_query(current_query)
                continue

            yield {"type": "step", "step": "grading", "content": "Evaluating relevance of results..."}
            relevant = self._grade_relevance(current_query, chunks)
            top_score = chunks[0].score if chunks else 0
            logger.info("[AgenticRAG] Relevance grading: relevant=%s (top score=%.3f)", relevant, top_score)
            if relevant:
                all_chunks = chunks
                break

            yield {"type": "step", "step": "decomposing", "content": "Results not relevant, decomposing into sub-questions..."}
            sub_queries = self._decompose_query(current_query)
            logger.info("[AgenticRAG] Decomposed into %d sub-queries", len(sub_queries) if sub_queries else 0)
            if sub_queries:
                for sq in sub_queries:
                    all_chunks.extend(self._retrieve(sq, collections, top_k))

            yield {"type": "step", "step": "rewriting", "content": "Rewriting query for better results..."}
            current_query = self._rewrite_query(current_query)
            logger.info("[AgenticRAG] Rewritten query: '%s'", current_query[:50])

        if not all_chunks:
            all_chunks = self._retrieve(current_query, collections, top_k)

        # Deduplicate
        seen: set[str] = set()
        unique: list[RetrievedChunk] = []
        for c in all_chunks:
            if c.text not in seen:
                seen.add(c.text)
                unique.append(c)
        all_chunks = unique

        # Rerank
        if self.reranker and all_chunks:
            yield {"type": "step", "step": "reranking", "content": f"Reranking {len(all_chunks)} results..."}
            try:
                all_chunks = self.reranker.rerank(query, all_chunks, top_k=result_top_k)
            except Exception:
                pass

        yield all_chunks[:result_top_k], current_query

    def run(
        self,
        query: str,
        collections: list[str] | str = "default",
        top_k: int = 5,
        max_iterations: int | None = None,
        rerank_top_k: int | None = None,
    ) -> AgentResult:
        if isinstance(collections, str):
            collections = [collections]
        max_iter = max_iterations or self.max_iterations
        rtk = rerank_top_k if rerank_top_k is not None else self.rerank_top_k

        # Consume generator: ignore step events, capture final result
        gen = self._run_retrieval(query, collections, top_k, max_iter, rerank_top_k=rtk)
        all_chunks, current_query = None, query
        for event in gen:
            if isinstance(event, tuple) and len(event) == 2 and isinstance(event[0], list):
                all_chunks, current_query = event
        if all_chunks is None:
            all_chunks = []
        return self._synthesize(query, all_chunks, current_query)

    def run_stream(
        self,
        query: str,
        collections: list[str] | str = "default",
        top_k: int = 5,
        max_iterations: int | None = None,
        rerank_top_k: int | None = None,
    ):
        """Streaming version — yields step events in real-time, then (result, stream)."""
        if isinstance(collections, str):
            collections = [collections]
        max_iter = max_iterations or self.max_iterations
        rtk = rerank_top_k if rerank_top_k is not None else self.rerank_top_k

        # Consume generator: yield step events immediately
        gen = self._run_retrieval(query, collections, top_k, max_iter, rerank_top_k=rtk)
        all_chunks, current_query = None, query
        for event in gen:
            if isinstance(event, dict):
                yield event, None
            elif isinstance(event, tuple) and len(event) == 2 and isinstance(event[0], list):
                all_chunks, current_query = event
        if all_chunks is None:
            all_chunks = []

        sources = [
            {"text": c.text, "score": c.score, "metadata": c.metadata}
            for c in all_chunks
        ]

        if not all_chunks:
            result = AgentResult(
                answer="I couldn't find relevant information for your query.",
                sources=[],
                iterations=max_iter,
                query_used=current_query,
            )
            yield result, iter([])
            return

        yield {"type": "step", "step": "generating", "content": f"Generating answer from {len(all_chunks)} sources..."}, None
        context = build_context(all_chunks)
        result = AgentResult(
            answer="",
            sources=sources,
            iterations=max_iter,
            query_used=current_query,
        )
        yield result, self._generate_answer_stream(query, context)

    # ── Internal steps ───────────────────────────────────────────

    def _retrieve(self, query: str, collections: list[str], top_k: int) -> list[RetrievedChunk]:
        all_chunks: list[RetrievedChunk] = []
        for col in collections:
            is_pc = self.db and self.db.get_collection_config(col).get("chunk_mode") == "parent_child"
            emb = self.embedding_overrides.get(col)
            emb_dim = emb.dimensions if emb else "None"
            logger.info("[AgenticRAG] Retrieving from '%s': is_pc=%s, embedding_override=%s (dim=%s)",
                        col, is_pc, emb is not None, emb_dim)
            if is_pc:
                emb = self.embedding_overrides.get(col)
                chunks, _ = retrieve_parent_child(
                    query, col, top_k, embedding=emb, db=self.db, min_score=self.min_score,
                )
            else:
                emb = self.embedding_overrides.get(col)
                chunks = self.retriever.retrieve(
                    query, collection=col, top_k=top_k,
                    embedding_override=emb, search_mode=self.search_mode,
                    min_score=self.min_score,
                )
            logger.info("[AgenticRAG] Collection '%s': retrieved %d chunks", col, len(chunks))
            for c in chunks:
                c.metadata["collection"] = col
            all_chunks.extend(chunks)
        return all_chunks

    def _grade_relevance(self, query: str, chunks: list[RetrievedChunk]) -> bool:
        if not chunks:
            return False
        top_chunks = "\n---\n".join(c.text[:500] for c in chunks[:3])
        response = self.llm.generate(
            GRADE_USER.format(query=query, top_chunks=top_chunks),
            system=GRADE_SYSTEM,
            temperature=self.temperature,
        ).strip()
        try:
            result = _parse_json(response)
            if isinstance(result, dict) and "sufficient" in result:
                return bool(result["sufficient"])
        except (json.JSONDecodeError, ValueError):
            pass
        return "sufficient" in response.lower() and "not" not in response.lower()

    def _decompose_query(self, query: str) -> list[str]:
        response = self.llm.generate(
            DECOMPOSE_USER.format(query=query),
            system=DECOMPOSE_SYSTEM,
            temperature=self.temperature,
        )
        try:
            result = _parse_json(response)
            if isinstance(result, list) and result:
                return [str(s) for s in result if s]
            return []
        except (json.JSONDecodeError, ValueError):
            return []

    def _rewrite_query(self, query: str) -> str:
        return self.llm.generate(
            REWRITE_USER.format(query=query),
            system=REWRITE_SYSTEM,
            temperature=self.temperature,
        ).strip()

    def _synthesize(self, query: str, chunks: list[RetrievedChunk], query_used: str = "") -> AgentResult:
        sources = [
            {"text": c.text, "score": c.score, "metadata": c.metadata}
            for c in chunks
        ]

        if not chunks:
            return AgentResult(
                answer="I couldn't find relevant information for your query.",
                sources=[],
                iterations=self.max_iterations,
                query_used=query_used,
            )

        context = build_context(chunks)
        answer = self.llm.generate(
            GENERATE_USER.format(context=context[:4000], question=query),
            system=GENERATE_SYSTEM,
            temperature=self.temperature,
        ).strip()

        return AgentResult(
            answer=answer,
            sources=sources,
            iterations=self.max_iterations,
            query_used=query_used,
        )

    def _generate_answer_stream(self, question: str, context: str):
        yield from self.llm.generate_stream(
            GENERATE_USER.format(context=context[:4000], question=question),
            system=GENERATE_SYSTEM,
            temperature=self.temperature,
        )
