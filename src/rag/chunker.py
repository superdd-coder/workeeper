from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import re
import uuid
from dataclasses import dataclass, field

try:
    import regex
except ImportError:
    regex = None


@dataclass
class Chunk:
    text: str
    metadata: dict = field(default_factory=dict)
    parent_id: str | None = None
    chunk_type: str = "normal"  # "normal" | "parent" | "child"



def _estimate_tokens(text: str) -> int:
    """Conservative token estimate. CJK ≈ 1 tok/char, non-CJK ≈ 1 tok/2 chars."""
    if not text:
        return 0
    cjk = sum(1 for c in text if "一" <= c <= "鿿")
    non_cjk = len(text) - cjk
    return cjk + (non_cjk + 1) // 2


def _split_paragraphs(text: str) -> list[str]:
    """Split on double newlines (empty lines)."""
    parts = re.split(r"\n\s*\n", text)
    return [p.strip() for p in parts if p.strip()]


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences. Generalized boundary detection.

    Boundaries (in priority order):
    1. Strong: 。！？\n
    2. Medium: .;:| followed by space/newline
    3. Weak: closing brackets ), ], } followed by space/newline
    """
    if not text.strip():
        return []

    # Step 1: Split on strong boundaries (Chinese punctuation only)
    # Newlines are NOT sentence boundaries — they're handled by paragraph splitting.
    parts = re.split(r"(?<=[。！？])\s*", text)

    # Step 2: Split on medium boundaries (.;:|)
    # Exclude numbered list patterns like "1.", "2.", "12." — variable-length
    # lookbehind prevents splitting when a digit precedes the period.
    if regex is not None:
        _split_re = regex.compile(r"(?<=[.;:|])(?<!\d[.;:|])\s+")
        _split = _split_re.split
    else:
        _split = lambda s: re.split(r"(?<=[.;:|])\s+", s)
    result = []
    for part in parts:
        sub = _split(part)
        result.extend(sub)

    # Step 2b: Split on Chinese punctuation (；：、) — no trailing space required
    result = [s for seg in result for s in re.split(r"(?<=[；：])(?!\s)|(?<=、)", seg)]

    # Step 3: Split on weak boundaries (closing brackets followed by space/newline)
    final = []
    for seg in result:
        sub = re.split(r"(?<=[)\]}])\s{2,}", seg)
        final.extend(sub)

    return [s.strip() for s in final if s.strip()]


class TextChunker:
    """Fixed-size character-based chunker with sentence boundary awareness."""

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64):
        self.chunk_size = max(chunk_size, 1)
        self.chunk_overlap = min(chunk_overlap, self.chunk_size - 1)

    def chunk(self, text: str) -> list[str]:
        if not text.strip():
            return []

        chunks = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]

            if end < len(text):
                last_period = chunk.rfind("。")
                if last_period == -1:
                    last_period = chunk.rfind(".")
                if last_period > len(chunk) // 2:
                    end = start + last_period + 1
                    chunk = text[start:end]

            chunks.append(chunk.strip())
            start = max(start + 1, end - self.chunk_overlap)

        return [c for c in chunks if c]

    def chunk_with_metadata(
        self, text: str, source: str = "", extra_metadata: dict | None = None
    ) -> list[Chunk]:
        raw_chunks = self.chunk(text)
        meta = {"source": source, **(extra_metadata or {})}
        total = len(raw_chunks)
        offset = 0
        chunks = []
        for i, c in enumerate(raw_chunks):
            chunks.append(
                Chunk(
                    text=c,
                    metadata={**meta, "chunk_index": i, "total_chunks": total, "char_offset": offset},
                )
            )
            offset += len(c)
        return chunks


class ParagraphChunker:
    """Smart paragraph-based chunker with sentence-level overlap.

    Strategy (preserves original paragraph-aware logic):
    - Split text into paragraphs (double newline separated)
    - Merge consecutive paragraphs until reaching max_tokens
    - If a single paragraph exceeds hard_limit (max_tokens × (1+buffer_ratio)), split it
      using 3-level fallback: line → sentence → token
    - If a single paragraph is between max_tokens and hard_limit, keep it whole (buffer tolerance)
    - Sentence-level overlap: keep the last N sentences from previous chunk (>= 1 sentence)
    """

    def __init__(self, max_tokens: int = 512, buffer_ratio: float = 0.5, chunk_overlap: int = 0):
        self.max_tokens = max(max_tokens, 1)
        self.buffer_ratio = max(buffer_ratio, 0.0)
        self.hard_limit = int(self.max_tokens * (1 + self.buffer_ratio))
        self.chunk_overlap = max(chunk_overlap, 0)

    def _get_overlap_sentences(self, text: str) -> list[str]:
        """Extract the last N sentences from text for overlap.

        Limits:
        - At most 3 sentences
        - Total tokens <= chunk_overlap
        - If single sentence exceeds chunk_overlap, truncate it
        """
        if self.chunk_overlap <= 0:
            return []
        sentences = _split_sentences(text)
        if not sentences:
            return []

        # Collect sentences from the end, respecting limits
        result = []
        token_count = 0
        max_sentences = 3
        for sent in reversed(sentences):
            if len(result) >= max_sentences:
                break
            sent_tokens = _estimate_tokens(sent)

            # If this sentence would exceed limit
            if token_count + sent_tokens > self.chunk_overlap:
                # If no sentences yet, truncate this one to fit
                if not result:
                    truncated = self._truncate_to_tokens(sent, self.chunk_overlap)
                    if truncated:
                        result.insert(0, truncated)
                break

            result.insert(0, sent)
            token_count += sent_tokens
        return result

    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """Truncate text to fit within max_tokens, keeping the END of the text.

        For overlap context, the end of the sentence is more relevant (closer to the
        current chunk), so we keep the tail and find a clean break point in it.
        """
        if _estimate_tokens(text) <= max_tokens:
            return text

        # Count tokens from the end to find how many characters to keep.
        tok = 0
        n = 0
        cut_from = 0
        for i in range(len(text) - 1, -1, -1):
            ch = text[i]
            if "一" <= ch <= "鿿":
                tok += 1
            else:
                n += 1
                if n % 2 == 0:
                    tok += 1
            if tok >= max_tokens:
                cut_from = i
                break

        if cut_from <= 0:
            return text

        kept = text[cut_from:]
        # Try to break at a clean boundary in the kept portion (start from the left)
        for sep in ["。", "！", "？", "；", "：", "、", ". ", "! ", "? ", "; ", ": ", ", "]:
            idx = kept.find(sep)
            if idx != -1 and idx < len(kept) // 3:
                return kept[idx + len(sep):]
        # No sentence boundary — try word boundary (space)
        space = kept.find(" ")
        if 0 < space < len(kept) // 3:
            return kept[space + 1:]
        # Hard cut
        return kept

    def chunk(self, text: str) -> list[str]:
        if not text.strip():
            return []

        paragraphs = _split_paragraphs(text)
        if not paragraphs:
            return []

        chunks: list[str] = []
        current_parts: list[str] = []
        current_tokens = 0

        for para in paragraphs:
            para_tokens = _estimate_tokens(para)

            # Case 1: paragraph alone exceeds hard_limit — must split it
            if para_tokens > self.hard_limit:
                if current_parts:
                    chunk_text = "\n\n".join(current_parts)
                    chunks.append(chunk_text)
                    overlap = self._get_overlap_sentences(chunk_text)
                    current_parts = list(overlap)
                    current_tokens = sum(_estimate_tokens(s) for s in current_parts)
                # Split the oversized paragraph using 3-level fallback
                chunks.extend(self._split_long_paragraph(para))
                continue

            # Case 2: adding this paragraph would exceed max_tokens — flush
            if current_parts and current_tokens + para_tokens > self.max_tokens:
                chunk_text = "\n\n".join(current_parts)
                chunks.append(chunk_text)
                overlap = self._get_overlap_sentences(chunk_text)
                current_parts = list(overlap)
                current_tokens = sum(_estimate_tokens(s) for s in current_parts)

            # Case 3: paragraph is within buffer tolerance (max_tokens ~ hard_limit) — keep whole
            current_parts.append(para)
            current_tokens += para_tokens

        # Flush remaining
        if current_parts:
            chunks.append("\n\n".join(current_parts))

        return [c for c in chunks if c.strip()]

    def _split_long_paragraph(self, text: str) -> list[str]:
        """Split a single long paragraph using sentence-aware merging.

        Strategy:
        1. Split into sentences (generalized boundary detection)
        2. Merge sentences into chunks with sentence-level overlap
        3. If single sentence exceeds hard_limit, split at token boundaries
        4. If no sentence boundaries found, fall back to token-level splitting
        """
        sentences = _split_sentences(text)

        # No sentence boundaries — token-level fallback
        if len(sentences) <= 1:
            return self._split_at_tokens(text)

        # Merge sentences into chunks with overlap
        chunks: list[str] = []
        current_parts: list[str] = []
        current_tokens = 0

        for sent in sentences:
            sent_tokens = _estimate_tokens(sent)

            # Single sentence exceeds hard_limit — split at token boundary
            if sent_tokens > self.hard_limit:
                if current_parts:
                    chunk_text = " ".join(current_parts)
                    chunks.append(chunk_text)
                    overlap = self._get_overlap_sentences(chunk_text)
                    current_parts = list(overlap)
                    current_tokens = sum(_estimate_tokens(s) for s in current_parts)
                chunks.extend(self._split_at_tokens(sent))
                continue

            # Adding this sentence would exceed max_tokens — flush
            if current_parts and current_tokens + sent_tokens > self.max_tokens:
                chunk_text = " ".join(current_parts)
                chunks.append(chunk_text)
                overlap = self._get_overlap_sentences(chunk_text)
                current_parts = list(overlap)
                current_tokens = sum(_estimate_tokens(s) for s in current_parts)

            current_parts.append(sent)
            current_tokens += sent_tokens

        # Flush remaining
        if current_parts:
            chunks.append(" ".join(current_parts))

        return [c for c in chunks if c.strip()]

    def _split_at_tokens(self, text: str) -> list[str]:
        """Last resort: split at token boundaries with sentence-boundary preference."""
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = start
            token_count = 0
            while end < len(text) and token_count < self.max_tokens:
                ch = text[end]
                if "一" <= ch <= "鿿":
                    token_count += 1
                else:
                    if (end - start) % 2 == 1:
                        token_count += 1
                end += 1

            # Try to break at sentence boundary, then word boundary
            if end < len(text):
                segment = text[start:end]
                last_break = max(
                    segment.rfind("。"), segment.rfind(". "),
                    segment.rfind("！"), segment.rfind("！"),
                    segment.rfind("？"), segment.rfind("？"),
                    segment.rfind("；"), segment.rfind("; "),
                    segment.rfind("："), segment.rfind(": "),
                    segment.rfind("、"),
                )
                if last_break > len(segment) // 3:
                    end = start + last_break + 1
                else:
                    # No sentence boundary — try word boundary (space, for non-CJK)
                    last_space = segment.rfind(" ")
                    if last_space > len(segment) // 3:
                        end = start + last_space + 1

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start = max(start + 1, end)

        return chunks

    def chunk_with_metadata(
        self, text: str, source: str = "", extra_metadata: dict | None = None
    ) -> list[Chunk]:
        raw_chunks = self.chunk(text)
        meta = {"source": source, **(extra_metadata or {})}
        total = len(raw_chunks)
        offset = 0
        chunks = []
        for i, c in enumerate(raw_chunks):
            chunks.append(
                Chunk(
                    text=c,
                    metadata={**meta, "chunk_index": i, "total_chunks": total, "char_offset": offset},
                )
            )
            offset += len(c)
        return chunks


class ParentChildChunker:
    """Splits documents into parent chunks (for context) and child chunks (for matching).

    At query time, child chunks are matched but parent chunks are returned to the LLM.
    """

    def __init__(
        self,
        parent_strategy: str = "paragraph",
        parent_chunk_size: int = 1024,
        parent_overlap: int = 128,
        parent_buffer_ratio: float = 0.5,
        child_chunk_size: int = 128,
        child_overlap: int = 32,
        child_buffer_ratio: float = 0.5,
    ):
        self.parent_strategy = parent_strategy
        self.parent_chunk_size = parent_chunk_size
        self.parent_overlap = parent_overlap
        self.parent_buffer_ratio = parent_buffer_ratio
        self.child_chunker = ParagraphChunker(
            max_tokens=child_chunk_size, buffer_ratio=child_buffer_ratio, chunk_overlap=child_overlap
        )

    def _split_paragraphs(self, text: str) -> list[str]:
        """Split on double newlines (empty lines)."""
        parts = re.split(r"\n\s*\n", text)
        return [p.strip() for p in parts if p.strip()]

    def _split_fixed_token(self, text: str) -> list[str]:
        """Split at fixed token boundaries. Approximate: 1 token ~ 2 chars for English, 4 for Chinese."""
        chars_per_token = 3
        target_chars = self.parent_chunk_size * chars_per_token
        overlap_chars = self.parent_overlap * chars_per_token

        if len(text) <= target_chars:
            return [text] if text.strip() else []

        chunks = []
        start = 0
        while start < len(text):
            end = min(start + target_chars, len(text))
            # Try to break at sentence boundary
            if end < len(text):
                chunk = text[start:end]
                last_period = chunk.rfind("。")
                if last_period == -1:
                    last_period = chunk.rfind(".")
                if last_period > len(chunk) // 2:
                    end = start + last_period + 1
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            # If we've reached the end, stop
            if end >= len(text):
                break
            start = max(start + 1, end - overlap_chars)

        return chunks

    def _split_headings(self, text: str) -> list[str]:
        """Split on markdown headings (#, ##, ###, etc.)."""
        pattern = r"(?=^#{1,6}\s)"
        parts = re.split(pattern, text, flags=re.MULTILINE)
        return [p.strip() for p in parts if p.strip()]

    def _split_parents(self, text: str) -> list[str]:
        """Split text into parent chunks using the chosen strategy."""
        if self.parent_strategy == "paragraph":
            paragraph_chunker = ParagraphChunker(
                max_tokens=self.parent_chunk_size, buffer_ratio=self.parent_buffer_ratio,
                chunk_overlap=self.parent_overlap,
            )
            return paragraph_chunker.chunk(text)
        elif self.parent_strategy == "fixed_token":
            return self._split_fixed_token(text)
        elif self.parent_strategy == "heading":
            return self._split_headings(text)
        else:
            paragraph_chunker = ParagraphChunker(
                max_tokens=self.parent_chunk_size, buffer_ratio=self.parent_buffer_ratio
            )
            return paragraph_chunker.chunk(text)

    def chunk_with_metadata(
        self, text: str, source: str = "", extra_metadata: dict | None = None
    ) -> list[Chunk]:
        """Returns both parent and child chunks."""
        parent_texts = self._split_parents(text)
        meta = {"source": source, **(extra_metadata or {})}

        all_chunks: list[Chunk] = []
        parent_offset = 0

        for parent_idx, parent_text in enumerate(parent_texts):
            parent_id = str(uuid.uuid4())

            # Create parent chunk
            parent_chunk = Chunk(
                text=parent_text,
                metadata={
                    **meta,
                    "chunk_id": parent_id,
                    "chunk_index": parent_idx,
                    "char_offset": parent_offset,
                },
                parent_id=None,
                chunk_type="parent",
            )
            all_chunks.append(parent_chunk)

            # Split parent into child chunks
            child_texts = self.child_chunker.chunk(parent_text)
            child_total = len(child_texts)
            child_offset = 0
            for child_idx, child_text in enumerate(child_texts):
                child_chunk = Chunk(
                    text=child_text,
                    metadata={
                        **meta,
                        "chunk_id": str(uuid.uuid4()),
                        "chunk_index": child_idx,
                        "total_chunks": child_total,
                        "char_offset": child_offset,
                    },
                    parent_id=parent_id,
                    chunk_type="child",
                )
                all_chunks.append(child_chunk)
                child_offset += len(child_text)

            parent_offset += len(parent_text)

        # Set total_chunks on parent chunks
        parent_count = len(parent_texts)
        for c in all_chunks:
            if c.chunk_type == "parent":
                c.metadata["total_chunks"] = parent_count

        return all_chunks
