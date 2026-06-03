from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from src.parsers import parse_file
from src.rag.collection_utils import build_context
from src.rag.agent import AgenticRAG, AgentResult

app = Server("workeeper")

_initialized = False
_init_lock = asyncio.Lock()


async def _ensure_services():
    global _initialized
    if not _initialized:
        async with _init_lock:
            if not _initialized:
                from src.services import init_services
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, init_services)
                _initialized = True
    from src.services import services
    return services


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="rag_query",
            description="Query the RAG knowledge base. Returns an answer with sources.",
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The question to ask"},
                    "collection": {"type": "string", "default": "default", "description": "Collection name"},
                    "use_agent": {"type": "boolean", "default": True},
                },
                "required": ["question"],
            },
        ),
        Tool(
            name="rag_upload_document",
            description="Upload and index a document into the RAG knowledge base.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the document file"},
                    "collection": {"type": "string", "default": "default"},
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="rag_delete_document",
            description="Delete a document from the RAG knowledge base by source path.",
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "collection": {"type": "string", "default": "default"},
                },
                "required": ["source"],
            },
        ),
        Tool(
            name="rag_list_collections",
            description="List all collections in the RAG knowledge base.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="rag_collection_info",
            description="Get info about a collection (document count, status).",
            inputSchema={
                "type": "object",
                "properties": {"collection": {"type": "string"}},
                "required": ["collection"],
            },
        ),
        Tool(
            name="rag_create_collection",
            description="Create a new collection in the RAG knowledge base.",
            inputSchema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    logger.info("MCP tool: %s", name)
    svc = await _ensure_services()
    loop = asyncio.get_running_loop()

    if name == "rag_query":
        def _query():
            if arguments.get("use_agent", True):
                if svc.llm is None or svc.retriever is None:
                    return {"error": "Agentic RAG not configured (LLM and retriever required)"}
                agent = AgenticRAG(
                    llm=svc.llm,
                    retriever=svc.retriever,
                    reranker=svc.reranker,
                    max_iterations=3,
                    db=svc.db,
                )
                result = agent.run(
                    query=arguments["question"],
                    collections=[arguments.get("collection", "default")],
                )
            else:
                chunks = svc.retriever.retrieve(
                    query=arguments["question"],
                    collection=arguments.get("collection", "default"),
                    top_k=svc.config.rag.rerank_top_k,
                )
                context = build_context(chunks)
                answer = svc.llm.generate(
                    f"Answer based on context:\n{context}\n\nQuestion: {arguments['question']}"
                )
                result = AgentResult(
                    answer=answer,
                    sources=[{"text": c.text, "score": c.score} for c in chunks],
                    iterations=1,
                    query_used=arguments["question"],
                )
            return {
                "answer": result.answer,
                "sources": result.sources[:5],
                "iterations": result.iterations,
            }

        response = await loop.run_in_executor(None, _query)
        return [TextContent(type="text", text=json.dumps(response, ensure_ascii=False, indent=2))]

    elif name == "rag_upload_document":
        file_path = Path(arguments["file_path"])
        if not file_path.exists():
            return [TextContent(type="text", text=f"Error: File not found: {file_path}")]

        def _upload():
            collection = arguments.get("collection", "default")
            if not svc.db.collection_exists(collection):
                svc.db.create_collection(collection, vector_size=svc.embedding.dimensions)

            doc = parse_file(file_path)

            # Use per-collection chunker
            col_config = svc.db.get_collection_config(collection)
            if col_config.get("chunk_mode") == "parent_child":
                from src.rag.chunker import ParentChildChunker
                chunker = ParentChildChunker(
                    parent_strategy=col_config.get("parent_strategy", "paragraph"),
                    parent_chunk_size=col_config.get("parent_chunk_size", 1024),
                    parent_overlap=col_config.get("parent_chunk_overlap", 128),
                    parent_buffer_ratio=col_config.get("buffer_ratio", 0.5),
                    child_chunk_size=col_config.get("child_chunk_size", 128),
                    child_overlap=col_config.get("child_chunk_overlap", 32),
                    child_buffer_ratio=col_config.get("buffer_ratio", 0.5),
                )
            else:
                from src.rag.chunker import ParagraphChunker
                chunker = ParagraphChunker(
                    max_tokens=col_config.get("chunk_size", 512),
                    buffer_ratio=col_config.get("buffer_ratio", 0.5),
                    chunk_overlap=col_config.get("chunk_overlap", 64),
                )

            chunks = chunker.chunk_with_metadata(doc.content, source=str(file_path), extra_metadata={"file_type": doc.file_type})

            if col_config.get("contextual_enabled", True) and svc.contextual is not None:
                chunks = svc.contextual.add_context(chunks, full_document=doc.content)

            texts = [c.text for c in chunks]
            embeddings = svc.embedding.embed_texts(texts)
            ids = []
            for c in chunks:
                if c.chunk_type in ("parent", "child"):
                    ids.append(c.metadata["chunk_id"])
                else:
                    new_id = str(uuid.uuid4())
                    c.metadata["chunk_id"] = new_id
                    ids.append(new_id)
            payloads = [{"text": c.text, **c.metadata} for c in chunks]

            svc.db.upsert_points(collection=collection, ids=ids, vectors=embeddings, payloads=payloads)
            return f"Uploaded {file_path.name}: {len(chunks)} chunks indexed to '{collection}'"

        msg = await loop.run_in_executor(None, _upload)
        return [TextContent(type="text", text=msg)]

    elif name == "rag_delete_document":
        def _delete():
            collection = arguments.get("collection", "default")
            svc.db.delete_by_filter(collection, key="source", value=arguments["source"])
            return f"Deleted document chunks from '{collection}'"

        msg = await loop.run_in_executor(None, _delete)
        return [TextContent(type="text", text=msg)]

    elif name == "rag_list_collections":
        collections = await loop.run_in_executor(None, svc.db.list_collections)
        return [TextContent(type="text", text=json.dumps(collections))]

    elif name == "rag_collection_info":
        def _info():
            return svc.db.get_collection_info(arguments["collection"])

        info = await loop.run_in_executor(None, _info)
        return [TextContent(type="text", text=json.dumps(info, default=str))]

    elif name == "rag_create_collection":
        def _create():
            col_name = arguments["name"]
            if svc.db.collection_exists(col_name):
                return f"Collection '{col_name}' already exists"
            if svc.embedding is None:
                return "Error: Embedding provider not configured"
            svc.db.create_collection(col_name, vector_size=svc.embedding.dimensions)
            return f"Collection '{col_name}' created"

        msg = await loop.run_in_executor(None, _create)
        return [TextContent(type="text", text=msg)]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def run_mcp_server():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def main():
    asyncio.run(run_mcp_server())


if __name__ == "__main__":
    main()
