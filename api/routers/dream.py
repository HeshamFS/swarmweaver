"""Dream task (memory consolidation) API endpoints."""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query, HTTPException

router = APIRouter()


@router.get("/api/dream/status")
async def get_dream_status(
    path: str = Query(..., description="Project directory path"),
):
    """Get dream consolidation status for a project."""
    from services.dream_daemon import get_daemon
    daemon = get_daemon()
    if not daemon:
        return {"status": "daemon_not_running", "gates": {}}
    daemon.register_project(Path(path))
    return {"status": "ok", "gates": daemon.get_status(Path(path))}


@router.post("/api/dream/trigger")
async def trigger_dream(
    path: str = Query(..., description="Project directory path"),
):
    """Manually trigger memory consolidation."""
    from services.dream_daemon import get_daemon
    daemon = get_daemon()
    if not daemon:
        raise HTTPException(status_code=503, detail="Dream daemon not running")
    daemon.register_project(Path(path))
    result = await daemon.trigger_manual(Path(path))
    return {"status": "ok", "result": result.to_dict()}


@router.get("/api/dream/history")
async def get_dream_history(
    path: str = Query(..., description="Project directory path"),
):
    """Get consolidation run history."""
    from services.dream_daemon import get_daemon
    daemon = get_daemon()
    if not daemon:
        return {"history": []}
    status = daemon.get_status(Path(path))
    return {"history": status.get("history", [])}


@router.get("/api/dream/config")
async def get_dream_config():
    """Get dream daemon configuration."""
    from services.dream_daemon import get_daemon
    daemon = get_daemon()
    if not daemon:
        from services.dream_consolidator import DreamConfig
        cfg = DreamConfig()
        return {"enabled": cfg.enabled, "time_gate_hours": cfg.time_gate_hours,
                "session_gate_count": cfg.session_gate_count}
    return daemon.get_config()
