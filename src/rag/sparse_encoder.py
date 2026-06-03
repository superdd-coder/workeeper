"""BM25 sparse encoder for hybrid search.

Lightweight implementation: whitespace tokenization + character bigrams for CJK.
Returns sparse vectors as {term_id: weight} dicts.
"""

from __future__ import annotations

import math
import re
from collections import Counter


def _tokenize(text: str) -> list[str]:
    """Tokenize text: lowercase, split on whitespace/punctuation, add char bigrams for CJK."""
    text = text.lower()
    tokens = re.findall(r"[a-z0-9]+|[一-鿿]", text)
    # Add character bigrams for Chinese characters
    cjk_chars = re.findall(r"[一-鿿]", text)
    for i in range(len(cjk_chars) - 1):
        tokens.append(cjk_chars[i] + cjk_chars[i + 1])
    return tokens


class SparseEncoder:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.term_to_id: dict[str, int] = {}
        self.doc_freqs: dict[int, int] = {}
        self.avg_dl: float = 0.0
        self._doc_count: int = 0

    def build_vocab(self, texts: list[str]) -> None:
        """Build vocabulary and document frequencies from a corpus."""
        if not texts:
            return

        for text in texts:
            tokens = _tokenize(text)
            for t in set(tokens):
                if t not in self.term_to_id:
                    self.term_to_id[t] = len(self.term_to_id)
                tid = self.term_to_id[t]
                self.doc_freqs[tid] = self.doc_freqs.get(tid, 0) + 1

        self._doc_count += len(texts)
        total_len = sum(len(_tokenize(t)) for t in texts)
        self.avg_dl = total_len / self._doc_count if self._doc_count else 1.0

    def encode(self, texts: list[str]) -> list[dict[int, float]]:
        """Encode texts into BM25 sparse vectors. Builds vocabulary on first call."""
        if not texts:
            return []

        self.build_vocab(texts)

        vectors = []
        for text in texts:
            tokens = _tokenize(text)
            vec = self._compute_bm25(tokens)
            vectors.append(vec)
        return vectors

    def encode_query(self, query: str) -> dict[int, float]:
        """Encode a query into BM25 sparse vector using stored vocabulary."""
        tokens = _tokenize(query)
        vec = {}
        for t in tokens:
            tid = self.term_to_id.get(t)
            if tid is None:
                continue
            vec[tid] = vec.get(tid, 0) + 1

        # Apply IDF weighting
        weighted = {}
        for tid, tf in vec.items():
            df = self.doc_freqs.get(tid, 0)
            idf = math.log((self._doc_count - df + 0.5) / (df + 0.5) + 1)
            weighted[tid] = tf * idf
        return weighted

    def _compute_bm25(self, tokens: list[str]) -> dict[int, float]:
        """Compute BM25 vector for a document's tokens."""
        tf = Counter(tokens)
        dl = len(tokens)

        vec = {}
        for t, count in tf.items():
            tid = self.term_to_id.get(t)
            if tid is None:
                continue
            df = self.doc_freqs.get(tid, 0)
            idf = math.log((self._doc_count - df + 0.5) / (df + 0.5) + 1)
            numerator = count * (self.k1 + 1)
            denominator = count + self.k1 * (1 - self.b + self.b * dl / max(self.avg_dl, 1))
            vec[tid] = idf * numerator / denominator
        return vec
