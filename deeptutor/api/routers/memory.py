"""
Two-file public memory API: SUMMARY and PROFILE.

When mem0 is enabled, manual edits are synced back to the vector store
and a semantic search endpoint is available.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from deeptutor.services.memory import MemoryFile, get_memory_service
from deeptutor.services.session import get_sqlite_session_store

router = APIRouter()

_VALID_FILES: set[MemoryFile] = {"summary", "profile"}


def _snap_dict(snap) -> dict:
    return {
        "summary": snap.summary,
        "profile": snap.profile,
        "summary_updated_at": snap.summary_updated_at,
        "profile_updated_at": snap.profile_updated_at,
    }


class FileUpdateRequest(BaseModel):
    file: MemoryFile
    content: str = ""


class MemoryRefreshRequest(BaseModel):
    session_id: str | None = None
    language: str = "en"


class MemoryClearRequest(BaseModel):
    file: MemoryFile | None = None


@router.get("")
async def get_memory():
    return _snap_dict(get_memory_service().read_snapshot())


@router.put("")
async def update_memory(payload: FileUpdateRequest):
    if payload.file not in _VALID_FILES:
        raise HTTPException(status_code=400, detail=f"Invalid file: {payload.file}")
    svc = get_memory_service()
    snap = svc.write_file(payload.file, payload.content)

    # Sync manual edit back to mem0 (manual > auto)
    try:
        await svc.sync_file_to_provider(payload.file)
    except Exception:
        pass  # Non-critical; file is already saved

    return {**_snap_dict(snap), "saved": True}


@router.post("/refresh")
async def refresh_memory(payload: MemoryRefreshRequest):
    store = get_sqlite_session_store()
    session_id = str(payload.session_id or "").strip()
    if session_id:
        session = await store.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")

    result = await get_memory_service().refresh_from_session(
        session_id or None,
        language=payload.language,
    )
    snap = get_memory_service().read_snapshot()
    return {**_snap_dict(snap), "changed": result.changed}


@router.post("/clear")
async def clear_memory(payload: MemoryClearRequest | None = None):
    svc = get_memory_service()
    target = payload.file if payload else None
    if target and target not in _VALID_FILES:
        raise HTTPException(status_code=400, detail=f"Invalid file: {target}")

    if target:
        snap = svc.clear_file(target)
    else:
        snap = svc.clear_memory()

    # Also clear mem0 records
    svc.clear_provider_memories()

    return {**_snap_dict(snap), "cleared": True}


@router.get("/search")
async def search_memory(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=100),
):
    """Semantic search over long-term memory records (mem0)."""
    svc = get_memory_service()
    records = svc.search(q, limit=limit)
    return {
        "results": [asdict(r) for r in records],
        "count": len(records),
    }
