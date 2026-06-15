"""Agentic RAG global state dataclass — flows through all pipeline nodes."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.rag.retriever import RetrievedChunk


@dataclass
class AgentState:
    """Global state flowing through all pipeline nodes.

    Mutated in-place by each node function during the orchestration loop.
    """

    # ── Immutable inputs ────────────────────────────────────────────
    original_query: str = ""
    collections: list[str] = field(default_factory=list)

    # ── Mutable query state ─────────────────────────────────────────
    current_query: str = ""
    history_queries: list[str] = field(default_factory=list)  # full past queries for dedup

    # ── Chunk tracking ──────────────────────────────────────────────
    all_chunks: list[RetrievedChunk] = field(default_factory=list)  # "elite pool"
    retained_chunks: list[RetrievedChunk] = field(default_factory=list)  # "golden context"
    seen_chunk_ids: set[str] = field(default_factory=set)  # Qdrant point IDs across all iterations

    # ── LLM grading output ──────────────────────────────────────────
    current_gap_analysis: str = ""
    is_sufficient: bool = False

    # ── Iteration control ───────────────────────────────────────────
    iteration_count: int = 0
    max_iterations: int = 3

    # ── Phase tracking ──────────────────────────────────────────────
    phase: str = "rewrite"  # "rewrite" | "decompose" | "synthesize"

    # ── Parameters (carried for node access) ────────────────────────
    top_k: int = 5
    rerank_top_k: int = 5
