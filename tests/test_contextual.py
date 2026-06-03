from unittest.mock import MagicMock
from src.rag.contextual import ContextualRetrieval
from src.rag.chunker import Chunk


def test_add_context():
    llm = MagicMock()
    llm.generate.return_value = "This document discusses Python programming."

    cr = ContextualRetrieval(llm=llm, context_window=1)
    chunks = [
        Chunk(text="Python is a popular language.", metadata={"chunk_index": 0, "source": "test.txt"}),
        Chunk(text="It supports multiple paradigms.", metadata={"chunk_index": 1, "source": "test.txt"}),
    ]
    result = cr.add_context(chunks, full_document="Python is a popular language. It supports multiple paradigms.")

    assert len(result) == 2
    assert "context" in result[0].metadata
    llm.generate.assert_called()
