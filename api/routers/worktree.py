"""Worktree management endpoints."""

from pathlib import Path

from fastapi import APIRouter, Query

router = APIRouter()


@router.post("/api/worktree/merge")
async def worktree_merge(path: str = Query(..., description="Original project directory"),
                          run_id: str = Query(..., description="Worktree run ID")):
    """Merge worktree branch into main branch."""
    try:
        from core.worktree import merge_worktree as _merge_wt
        result = _merge_wt(Path(path), run_id)
        return {
            "status": "ok" if result.success else "error",
            "files_changed": result.files_changed,
            "merge_output": result.merge_output[:500],
            "error": result.error,
            "resolution_tier": result.resolution_tier,
            "resolution_tier_name": result.resolution_tier_name,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.post("/api/worktree/discard")
async def worktree_discard(path: str = Query(..., description="Original project directory"),
                            run_id: str = Query(..., description="Worktree run ID")):
    """Discard worktree and delete branch."""
    try:
        from core.worktree import discard_worktree as _discard_wt
        success = _discard_wt(Path(path), run_id)
        return {"status": "ok" if success else "error"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.get("/api/worktree/diff")
async def worktree_diff(path: str = Query(..., description="Original project directory"),
                         run_id: str = Query(..., description="Worktree run ID")):
    """Get diff between worktree branch and original."""
    try:
        from core.worktree import get_worktree_diff as _get_diff, get_worktree_status as _get_status
        diff = _get_diff(Path(path), run_id)
        status = _get_status(Path(path), run_id)
        return {
            "diff": diff[:50000],
            "status": status.to_dict(),
        }
    except Exception as e:
        return {"diff": "", "status": {}, "error": str(e)}


@router.get("/api/worktree/status")
async def worktree_status(path: str = Query(..., description="Original project directory"),
                           run_id: str = Query(..., description="Worktree run ID")):
    """Get worktree status (files changed, insertions, deletions)."""
    try:
        from core.worktree import get_worktree_status as _get_status
        status = _get_status(Path(path), run_id)
        return {"status": status.to_dict()}
    except Exception as e:
        return {"status": {}, "error": str(e)}
