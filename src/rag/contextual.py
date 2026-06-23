from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

from concurrent.futures import ThreadPoolExecutor, as_completed
from src.providers.base import LLMProvider
from src.rag.chunker import Chunk

from src.prompts import CONTEXT_PROMPT, SUMMARY_PROMPT, STRUCTURED_SUMMARY_PROMPT  # noqa: E402

_executor = ThreadPoolExecutor(max_workers=10)


class ContextualRetrieval:
    def __init__(self, llm: LLMProvider, context_window: int = 1):
        self.llm = llm
        self.context_window = context_window

    def _generate_summary(self, document: str) -> str:
        prompt = SUMMARY_PROMPT.format(document=document)
        try:
            return self.llm.generate(prompt).strip()
        except Exception:
            return ""

    def _generate_context(self, summary: str, chunk_text: str, surrounding_text: str = "") -> str:
        # Skip context for very short chunks — they're self-contained
        if len(chunk_text.strip()) < 50:
            return ""
        surrounding_section = ""
        if surrounding_text:
            surrounding_section = f"Surrounding chunks (for context):\n{surrounding_text}\n\n"
        prompt = CONTEXT_PROMPT.format(
            summary=summary, chunk=chunk_text, surrounding_section=surrounding_section,
        )
        try:
            ctx = self.llm.generate(prompt).strip()
            if not ctx or ctx == summary:
                return ""
            return ctx
        except Exception:
            return ""

    def add_context(self, chunks: list[Chunk], full_document: str) -> list[Chunk]:
        # Step 1: Generate document summary
        summary = self._generate_summary(full_document)
        logger.info("Enrichment: generating context for %d chunks", len(chunks))

        # Step 2: Build surrounding context for each chunk
        chunk_texts = [c.text for c in chunks]

        def _get_surrounding(idx: int) -> str:
            """Get text from surrounding chunks within context_window."""
            parts = []
            for offset in range(-self.context_window, self.context_window + 1):
                neighbor_idx = idx + offset
                if neighbor_idx == idx or neighbor_idx < 0 or neighbor_idx >= len(chunk_texts):
                    continue
                parts.append(chunk_texts[neighbor_idx])
            return "\n...\n".join(parts) if parts else ""

        # Step 3: Generate context for each chunk in parallel
        def _gen(chunk: Chunk) -> tuple[int, str]:
            idx = chunk.metadata.get("chunk_index", 0)
            surrounding = _get_surrounding(idx) if self.context_window > 0 else ""
            ctx = self._generate_context(summary, chunk.text, surrounding)
            return idx, ctx

        results = {}
        futures = {_executor.submit(_gen, c): c for c in chunks}
        for future in as_completed(futures):
            idx, ctx = future.result()
            results[idx] = ctx

        # Step 3: Store context in metadata only (don't modify chunk.text)
        for chunk in chunks:
            idx = chunk.metadata.get("chunk_index", 0)
            context = results.get(idx, "")
            chunk.metadata["context"] = context
            chunk.metadata["summary"] = summary

        return chunks


# ---------------------------------------------------------------------------
# Structured Summary Generation
# ---------------------------------------------------------------------------



def _parse_structured_summary(raw: str) -> dict[str, list[str]]:
    """Parse LLM output into structured summary dict.

    Splits on ``===`` delimiters, extracts bullet items under DATA, FACTS,
    and INSIGHTS sections, and filters out "None identified" placeholders.

    Returns ``{"data": [...], "facts": [...], "insights": [...]}``.
    """
    if not raw or not raw.strip():
        return {"data": [], "facts": [], "insights": []}

    result: dict[str, list[str]] = {"data": [], "facts": [], "insights": []}
    section_map = {"data": "data", "facts": "facts", "insights": "insights"}

    current_key: str | None = None

    for line in raw.splitlines():
        stripped = line.strip()

        # Detect section headers like ===DATA=== or ===data===
        if stripped.startswith("===") and stripped.endswith("==="):
            header = stripped[3:-3].strip().lower()
            if header in section_map:
                current_key = section_map[header]
            else:
                current_key = None
            continue

        # Parse bullet items
        if current_key is not None and stripped.startswith("-"):
            item = stripped.lstrip("-").strip()
            if item and item.lower() != "none identified":
                result[current_key].append(item)

    return result


def generate_structured_summary(llm: LLMProvider, document: str) -> dict[str, list[str]]:
    """Generate a structured summary (data/facts/insights) from a document.

    Uses the LLM to extract three categories of information and returns
    a parsed dict.  Returns empty lists on any failure.
    """
    prompt = STRUCTURED_SUMMARY_PROMPT.format(document=document)
    try:
        raw = llm.generate(prompt)
    except Exception:
        return {"data": [], "facts": [], "insights": []}
    return _parse_structured_summary(raw)

