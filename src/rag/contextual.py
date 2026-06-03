from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

from concurrent.futures import ThreadPoolExecutor, as_completed
from src.providers.base import LLMProvider
from src.rag.chunker import Chunk

SUMMARY_PROMPT = """Write a brief 1-2 sentence summary of this document. Focus on: what is this document about, who is it for, and what is its purpose. Keep it concise and readable.

Document:
{document}"""

CONTEXT_PROMPT = """You are helping build a search index. Given a document summary, a chunk from that document, and its surrounding chunks, write 1-2 sentences of background context that a reader would need to understand this chunk but CANNOT figure out from the chunk text alone.

Document summary: {summary}

{surrounding_section}Chunk text: {chunk}

Rules:
- Only include information NOT present in the chunk itself
- Write in natural, readable sentences (not key=value format)
- Focus on: what section of the document this is from, what was discussed before this chunk, who/what entities are referenced
- Use surrounding chunks to understand what comes before/after this chunk
- If the chunk is self-contained and understandable on its own, output nothing
- Keep it brief — max 2 short sentences

Output only the context text, nothing else."""

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

STRUCTURED_SUMMARY_PROMPT = """Analyze the following document and extract key information. Be extremely conservative — only extract facts that are EXPLICITLY stated in the document. Do NOT infer, assume, or generalize.

Document:
{document}

Output in this exact format:

===DATA===
(Numerical data that is EXPLICITLY stated in the document with clear context)
- Example: The contract value for Project Alpha is 5 million USD
- Example: The system design capacity is 3,000 m3/day

===FACTS===
(Factual statements that are EXPLICITLY stated — not inferred)
- Example: Company X is the contractor for Project Alpha
- Example: The project uses Dow BW30-400 RO membranes

===INSIGHTS===
(Only include if there is STRONG direct evidence in the document. If uncertain, write "- None identified")
- Example: Based on the 3-month delay mentioned by the project manager, the Q3 deadline appears at risk

Rules:
- MAX 10 items per category. Quality over quantity.
- ONLY extract what is explicitly written. Do NOT generalize from examples or discussions.
- If a number or fact is mentioned in a hypothetical, example, or "what-if" scenario, do NOT treat it as a real data point.
- If you are not sure whether something is a fact or an assumption, do NOT include it.
- Each item MUST clearly state what it refers to. Do not use vague references like "the project" — name the specific project/entity.
- If a category has nothing that meets these criteria, write "- None identified"
- Do NOT use square brackets [] around words. Write plain sentences.
- Pay attention to context: if someone says "let's model a 1000 m3/day project", that is a discussion about modeling, NOT a statement about an actual project's capacity."""


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

