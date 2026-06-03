from __future__ import annotations

import logging

from fastapi import APIRouter, Body

from src.hot_words import store
from src.hot_words.models import HotWordsLibrary

logger = logging.getLogger("hot_words")
router = APIRouter(prefix="/api/hot-words", tags=["hot-words"])


@router.get("")
async def list_libraries():
    libs = store.list_libraries()
    return [
        {
            "id": lib.id,
            "name": lib.name,
            "description": lib.description,
            "word_count": len(lib.words),
            "created_at": lib.created_at,
            "updated_at": lib.updated_at,
        }
        for lib in libs
    ]


@router.get("/{library_id}")
async def get_library(library_id: str):
    lib = store.get_library(library_id)
    if lib is None:
        return {"error": "Hot words library not found"}
    return lib.model_dump()


@router.post("")
async def create_library(body: dict = Body()):
    name = body.get("name", "").strip()
    if not name:
        return {"error": "Name is required"}
    description = body.get("description", "")
    lib = store.create_library(name=name, description=description)
    return lib.model_dump()


@router.put("/{library_id}")
async def update_library(library_id: str, body: dict = Body()):
    try:
        lib = store.update_library(library_id, **body)
    except FileNotFoundError:
        return {"error": "Hot words library not found"}
    return lib.model_dump()


@router.delete("/{library_id}")
async def delete_library(library_id: str):
    deleted = store.delete_library(library_id)
    if not deleted:
        return {"error": "Hot words library not found"}
    return {"message": "Hot words library deleted"}
