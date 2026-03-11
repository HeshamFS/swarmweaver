"""Snapshots API — browse, diff, and revert shadow git snapshots."""

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
    """Manual garbage collection."""
    try:
        mgr = _get_manager(path)
        mgr.cleanup(max_age_days=max_age_days)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/snapshots/status")
async def snapshot_status(
    path: str = Query(..., description="Project directory"),
):
    """Snapshot system status."""
    try:
        mgr = _get_manager(path)
        return mgr.get_status()
    except Exception as e:
        return {"available": False, "error": str(e)}
