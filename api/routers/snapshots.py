"""Snapshots API — browse, diff, revert, bookmark, and restore shadow git snapshots."""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from state.snapshots import SnapshotManager

router = APIRouter()


def _get_manager(project_dir: str) -> SnapshotManager:
    return SnapshotManager(Path(project_dir))


class RevertRequest(BaseModel):
    hash: str
    files: list[str]


class RestoreRequest(BaseModel):
    hash: str


class BookmarkRequest(BaseModel):
    hash: str
    name: str
    description: str = ""


# ------------------------------------------------------------------
# Existing endpoints
# ------------------------------------------------------------------


@router.get("/api/snapshots")
async def list_snapshots(
    path: str = Query(..., description="Project directory"),
    session_id: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    """List snapshots for a project."""
    try:
        mgr = _get_manager(path)
        snapshots = mgr.list_snapshots(limit=limit, session_id=session_id)
        return {"snapshots": snapshots, "count": len(snapshots)}
    except Exception as e:
        return {"snapshots": [], "count": 0, "error": str(e)}


@router.get("/api/snapshots/diff")
async def diff_snapshots(
    path: str = Query(..., description="Project directory"),
    from_hash: str = Query(..., alias="from"),
    to_hash: Optional[str] = Query(None, alias="to"),
):
    """Diff between two snapshots (structured)."""
    try:
        mgr = _get_manager(path)
        result = mgr.diff(from_hash, to_hash)
        return result
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/snapshots/diff/file")
async def diff_file(
    path: str = Query(..., description="Project directory"),
    from_hash: str = Query(..., alias="from"),
    to_hash: str = Query(..., alias="to"),
    file: str = Query(..., description="File path to diff"),
):
    """Single file diff (unified)."""
    try:
        mgr = _get_manager(path)
        diff_text = mgr.diff_file(from_hash, to_hash, file)
        return {"diff": diff_text, "file": file}
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/snapshots/files")
async def changed_files(
    path: str = Query(..., description="Project directory"),
    from_hash: str = Query(..., alias="from"),
    to_hash: Optional[str] = Query(None, alias="to"),
):
    """Changed files between snapshots."""
    try:
        mgr = _get_manager(path)
        files = mgr.changed_files(from_hash, to_hash)
        return {"files": files, "count": len(files)}
    except Exception as e:
        return {"files": [], "count": 0, "error": str(e)}


@router.post("/api/snapshots/revert")
async def revert_files(
    path: str = Query(..., description="Project directory"),
    body: RevertRequest = ...,
):
    """Revert specific files from a snapshot."""
    try:
        mgr = _get_manager(path)
        result = mgr.revert_files(body.hash, body.files)
        return result
    except Exception as e:
        return {"error": str(e)}


@router.post("/api/snapshots/restore")
async def restore_snapshot(
    path: str = Query(..., description="Project directory"),
    body: RestoreRequest = ...,
):
    """Full restore to a snapshot."""
    try:
        mgr = _get_manager(path)
        success = mgr.restore(body.hash)
        return {"restored": success, "hash": body.hash}
    except Exception as e:
        return {"error": str(e)}


@router.post("/api/snapshots/cleanup")
async def cleanup_snapshots(
    path: str = Query(..., description="Project directory"),
    max_age_days: int = Query(7, ge=1, le=365),
):
    """Manual garbage collection (preserves bookmarked snapshots)."""
    try:
        mgr = _get_manager(path)
        removed = mgr.cleanup(max_age_days=max_age_days)
        return {"status": "ok", "removed": removed}
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/snapshots/status")
async def snapshot_status(
    path: str = Query(..., description="Project directory"),
):
    """Snapshot system status (includes bookmark count)."""
    try:
        mgr = _get_manager(path)
        return mgr.get_status()
    except Exception as e:
        return {"available": False, "error": str(e)}


# ------------------------------------------------------------------
# New: Bookmarks
# ------------------------------------------------------------------


@router.post("/api/snapshots/bookmark")
async def create_bookmark(
    path: str = Query(..., description="Project directory"),
    body: BookmarkRequest = ...,
):
    """Create a named bookmark for a snapshot (preserves it from cleanup)."""
    try:
        mgr = _get_manager(path)
        success = mgr.bookmark(body.hash, body.name, body.description)
        return {"created": success, "name": body.name, "hash": body.hash}
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/snapshots/bookmarks")
async def list_bookmarks(
    path: str = Query(..., description="Project directory"),
):
    """List all named bookmarks with snapshot metadata."""
    try:
        mgr = _get_manager(path)
        bookmarks = mgr.list_bookmarks()
        return {"bookmarks": bookmarks, "count": len(bookmarks)}
    except Exception as e:
        return {"bookmarks": [], "count": 0, "error": str(e)}


@router.delete("/api/snapshots/bookmark/{name}")
async def delete_bookmark(
    name: str,
    path: str = Query(..., description="Project directory"),
):
    """Delete a bookmark (the snapshot itself is preserved)."""
    try:
        mgr = _get_manager(path)
        success = mgr.delete_bookmark(name)
        return {"deleted": success, "name": name}
    except Exception as e:
        return {"error": str(e)}


# ------------------------------------------------------------------
# New: Preview & History
# ------------------------------------------------------------------


@router.get("/api/snapshots/preview-restore")
async def preview_restore(
    path: str = Query(..., description="Project directory"),
    hash: str = Query(..., description="Tree hash to preview restoring to"),
):
    """Preview what would change if restoring to a snapshot."""
    try:
        mgr = _get_manager(path)
        result = mgr.preview_restore(hash)
        return result
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/snapshots/history")
async def snapshot_history(
    path: str = Query(..., description="Project directory"),
    limit: int = Query(50, le=200),
):
    """Git commit history of the snapshot branch with metadata."""
    try:
        mgr = _get_manager(path)
        history = mgr.get_history(limit=limit)
        return {"history": history, "count": len(history)}
    except Exception as e:
        return {"history": [], "count": 0, "error": str(e)}


@router.get("/api/snapshots/{tree_hash}")
async def get_snapshot(
    tree_hash: str,
    path: str = Query(..., description="Project directory"),
):
    """Get a single snapshot by tree hash."""
    try:
        mgr = _get_manager(path)
        snapshot = mgr.get_snapshot(tree_hash)
        if not snapshot:
            return {"error": "Snapshot not found"}
        return snapshot
    except Exception as e:
        return {"error": str(e)}
