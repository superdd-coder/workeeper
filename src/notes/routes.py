"""Notes API routes — CRUD, content, distillation, and propagation."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Body, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from src.notes import store
from src.notes.service import distill_note, propagate_forward, parse_injection_blocks

logger = logging.getLogger("notes")
router = APIRouter()


# ── Notes CRUD ─────────────────────────────────────────────────


@router.get("/notes/{collection}")
async def list_notes(collection: str):
    """List all notes for a collection, sorted by updated_at descending."""
    notes = store.list_notes(collection)
    items = []
    for note in notes:
        referenced_by = store.get_referenced_by(collection, note.id)
        items.append({
            "id": note.id,
            "title": note.title,
            "collection": note.collection,
            "created_at": note.created_at.isoformat(),
            "updated_at": note.updated_at.isoformat(),
            "is_extracted": len(referenced_by) > 0,
            "extracted_into": referenced_by,
        })
    return {"collection": collection, "notes": items}


@router.post("/notes/{collection}")
async def create_note(collection: str, body: dict = Body()):
    """Create a new note in a collection."""
    title = body.get("title") or datetime.now().strftime("%Y-%m-%d %H:%M")
    logger.info("[CREATE] Note '%s' in collection '%s'", title, collection)
    note = store.create_note(collection, title)
    return {
        "id": note.id,
        "title": note.title,
        "collection": note.collection,
        "created_at": note.created_at.isoformat(),
        "updated_at": note.updated_at.isoformat(),
    }


@router.get("/notes/{collection}/{note_id}")
async def get_note(collection: str, note_id: str):
    """Get note metadata, content, and references."""
    note = store.get_note(collection, note_id)
    if not note:
        raise HTTPException(status_code=404, detail=f"Note {note_id} not found")
    content = store.get_content(collection, note_id) or ""
    references = store.get_references(collection, note_id)
    referenced_by = store.get_referenced_by(collection, note_id)
    # Enrich references with source titles
    for ref in references:
        source = store.get_note(collection, ref.get("source_note_id", ""))
        ref["source_title"] = source.title if source else ref.get("source_note_id", "")
    return {
        "id": note.id,
        "title": note.title,
        "collection": note.collection,
        "created_at": note.created_at.isoformat(),
        "updated_at": note.updated_at.isoformat(),
        "content": content,
        "references": references,
        "is_extracted": len(referenced_by) > 0,
        "extracted_into": referenced_by,
    }


@router.put("/notes/{collection}/{note_id}")
async def update_note(collection: str, note_id: str, body: dict = Body()):
    """Update note content and/or title. Auto-syncs injection block references."""
    note = store.get_note(collection, note_id)
    if not note:
        raise HTTPException(status_code=404, detail=f"Note {note_id} not found")

    # Update title if provided
    if "title" in body:
        store.update_note(collection, note_id, title=body["title"])

    # Update content if provided
    if "content" in body:
        content = body["content"]

        # Sync references — re-parse injection blocks from content
        # IMPORTANT: get old refs BEFORE saving new content
        old_refs = store.get_references(collection, note_id)
        old_source_ids = {r["source_note_id"] for r in old_refs}

        blocks = parse_injection_blocks(content)
        refs = []
        new_source_ids: set[str] = set()
        for block in blocks:
            source_id = block["source_note_id"]
            new_source_ids.add(source_id)
            source = store.get_note(collection, source_id)
            refs.append({
                "block_id": block["block_id"],
                "source_note_id": source_id,
                "source_title": source.title if source else "",
            })

        # Save the content and references
        store.save_content(collection, note_id, content)
        store.save_references(collection, note_id, refs)

        # Update referenced_by: diff old vs new sources
        for removed_source_id in old_source_ids - new_source_ids:
            store._remove_referenced_by(collection, removed_source_id, note_id)
        for added_source_id in new_source_ids - old_source_ids:
            store._add_referenced_by(collection, added_source_id, note_id)

    return {"message": "Note updated", "id": note_id}


@router.delete("/notes/{collection}/{note_id}")
async def delete_note(collection: str, note_id: str):
    """Delete a note and clean up all references."""
    logger.info("[DELETE] Note %s in collection '%s'", note_id, collection)
    deleted = store.delete_note(collection, note_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Note {note_id} not found")
    return {"message": "Note deleted"}


# ── Distillation ───────────────────────────────────────────────


@router.post("/notes/{collection}/{note_id}/distill")
async def distill_into_note(collection: str, note_id: str, body: dict = Body()):
    """Generate (or return cached) distillation of source_note for target note.
    The frontend is responsible for inserting the block into the content."""
    source_note_id = body.get("source_note_id")
    if not source_note_id:
        raise HTTPException(status_code=400, detail="source_note_id is required")

    source = store.get_note(collection, source_note_id)
    if not source:
        raise HTTPException(status_code=404, detail=f"Source note {source_note_id} not found")

    target = store.get_note(collection, note_id)
    if not target:
        raise HTTPException(status_code=404, detail=f"Target note {note_id} not found")

    logger.info("[DISTILL] %s → %s in collection '%s'", source_note_id, note_id, collection)

    # Generate distilled content (uses cache if available).
    # Run in thread pool — the LLM call is synchronous and blocks the
    # event loop, causing all other requests (getNote etc.) to queue.
    distilled = await asyncio.to_thread(distill_note, collection, source_note_id, note_id)

    block_id = uuid.uuid4().hex[:12]

    return {
        "message": "Distillation ready",
        "block_id": block_id,
        "source_note_id": source_note_id,
        "source_title": source.title,
        "distilled_content": distilled,
    }


# ── Propagation ────────────────────────────────────────────────


@router.get("/notes/{collection}/{note_id}/propagation-preview")
async def get_propagation_preview(collection: str, note_id: str):
    """Preview the full propagation chain if this note's content changes."""
    note = store.get_note(collection, note_id)
    if not note:
        raise HTTPException(status_code=404, detail=f"Note {note_id} not found")

    links = store.build_propagation_chain(collection, note_id)
    return {
        "origin_id": note_id,
        "origin_title": note.title,
        "links": links,
        "total_affected": len(links),
    }


@router.post("/notes/{collection}/{note_id}/propagate")
async def trigger_propagation(collection: str, note_id: str, background_tasks: BackgroundTasks):
    """Trigger backward propagation: re-distill this note into all notes that reference it.
    Chain propagation (downstream) is automatic and doesn't require user confirmation.
    Runs in background to avoid blocking."""
    note = store.get_note(collection, note_id)
    if not note:
        raise HTTPException(status_code=404, detail=f"Note {note_id} not found")

    # Run propagation in background to avoid blocking the response
    def run_propagation():
        logger.info("[PROPAGATE] Starting propagation from note %s in '%s'", note_id, collection)
        updated = propagate_forward(collection, note_id, auto=True)
        logger.info("[PROPAGATE] Updated %d notes: %s", len(updated), updated)

    background_tasks.add_task(run_propagation)

    return {
        "message": "Propagation started in background",
        "status": "started",
    }


# ── Image upload & serve ──────────────────────────────────────

IMAGES_DIR = Path("data").resolve() / "notes"


@router.post("/notes/{collection}/{note_id}/images")
async def upload_note_image(collection: str, note_id: str, file: UploadFile = File(...)):
    """Upload an image for a note. Returns the URL path to use in markdown."""
    note = store.get_note(collection, note_id)
    if not note:
        raise HTTPException(status_code=404, detail=f"Note {note_id} not found")

    content_bytes = await file.read()
    filename = file.filename or "image.png"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "png"
    safe_name = f"{uuid.uuid4().hex[:10]}.{ext}"

    images_dir = IMAGES_DIR / collection / note_id / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    image_path = images_dir / safe_name
    image_path.write_bytes(content_bytes)

    url = f"/api/notes/{collection}/{note_id}/images/{safe_name}"
    logger.info("[IMAGE] Uploaded %s (%d bytes) for note %s", safe_name, len(content_bytes), note_id)
    return {"url": url, "filename": safe_name}


@router.get("/notes/{collection}/{note_id}/images/{filename}")
async def serve_note_image(collection: str, note_id: str, filename: str):
    """Serve an uploaded image for a note."""
    image_path = IMAGES_DIR / collection / note_id / "images" / filename
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(str(image_path))
