from __future__ import annotations

import asyncio
import json
import logging

logger = logging.getLogger(__name__)


def _get_summary_manager():
    from src.services import services
    from src.rag.summary_manager import SummaryManager
    return SummaryManager(db=services.db)


async def get_collection_summary(collection: str) -> str:
    """Get the LLM-generated overview of a collection — summarizes all documents into a coherent briefing.

    Use this to quickly understand what a collection contains before diving into specific documents or querying.
    """
    def _run():
        sm = _get_summary_manager()
        summary = sm.get_collection_summary(collection)
        if summary is None:
            return {"error": f"No summary found for collection '{collection}'"}
        return summary

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _run)
    return json.dumps(result, ensure_ascii=False, default=str)


async def get_project_description(collection: str) -> str:
    """Get a 2-sentence description of what a collection covers.

    Quick way to understand a collection's scope without reading the full summary.
    """
    def _run():
        sm = _get_summary_manager()
        desc = sm.get_project_description(collection)
        if desc is None:
            return {"error": f"No project description found for collection '{collection}'"}
        return desc

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _run)
    return json.dumps(result, ensure_ascii=False, default=str)


async def get_doc_summary(collection: str, source: str) -> str:
    """Get the structured summary of a specific document — extracted data points, facts, and insights.

    Use `list_documents` to get available source filenames.
    """
    def _run():
        sm = _get_summary_manager()
        summary = sm.get_doc_summary(collection, source)
        if summary is None:
            return {"error": f"No summary found for document '{source}' in collection '{collection}'"}
        return summary

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _run)
    return json.dumps(result, ensure_ascii=False, default=str)


async def get_conflicts(collection: str) -> str:
    """Check for contradictory information across documents in a collection.

    Returns detected conflicts (e.g. different dates, conflicting numbers) so you can identify inconsistencies in the knowledge base.
    """
    def _run():
        sm = _get_summary_manager()
        conflicts = sm.get_conflicts(collection)
        if not conflicts:
            return {"collection": collection, "conflicts": [], "message": "No conflicts detected"}
        return {"collection": collection, "conflicts": conflicts}

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _run)
    return json.dumps(result, ensure_ascii=False, default=str)


async def trigger_consolidate(collection: str) -> str:
    """Rebuild the collection-level summary from all document summaries.

    Run this after uploading or deleting documents to refresh the collection overview, project description, and conflict report.
    Uses `get_task_status` to check completion.
    """
    from src.tasks import task_manager

    def _run():
        from src.services import services
        if not services.db.collection_exists(collection):
            return {"error": f"Collection '{collection}' does not exist"}
        task = task_manager.create_task(
            filename=f"consolidate:{collection}",
            task_type="consolidate",
            collection=collection,
        )
        return {"message": f"Consolidation triggered for '{collection}'", "task_id": task.id}

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _run)
    return json.dumps(result, ensure_ascii=False)
