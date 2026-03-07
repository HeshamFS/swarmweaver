"""Swarm, orchestrator, and approval endpoints."""

import json
import os
import signal
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query

from core.paths import get_paths
from api.state import _running_engines
from api.models import NudgeRequest, TerminateRequest

router = APIRouter()


@router.get("/api/swarm/status")
async def get_swarm_status(
    path: str = Query(..., description="Project directory path"),
):
    """Get current swarm state. Prefers live orchestrator state when active (Smart Swarm)."""
    # Prefer Smart Orchestrator when active — has assigned_task_ids and live worker data
    for mode in ("feature", "greenfield", "refactor", "fix", "evolve"):
        key = f"native_{mode}_{path}"
        runner = _running_engines.get(key)
        if runner and hasattr(runner, "get_state"):
            state = runner.get_state()
            if state.get("workers"):
                workers = state["workers"]
                # Normalize to format frontend expects: worker_id, name, status, assigned_task_ids, etc.
                return {
                    "num_workers": len(workers),
                    "workers": [
                        {
                            "worker_id": w.get("worker_id"),
                            "name": w.get("name"),
                            "status": w.get("status"),
                            "capability": w.get("role"),
                            "assigned_task_ids": w.get("assigned_task_ids", []),
                            "file_scope": w.get("file_scope", []),
                            "worktree_path": w.get("worktree_path"),
                            "branch_name": w.get("branch_name"),
                            "started_at": w.get("started_at"),
                            "completed_at": w.get("completed_at"),
                        }
                        for w in workers
                    ],
                }
            break

    # Fall back to swarm_state file (static Swarm)
    state_file = get_paths(Path(path)).swarm_state
    if state_file.exists():
        try:
            return json.loads(state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"num_workers": 0, "workers": []}


@router.get("/api/orchestrator/status")
async def get_orchestrator_status(
    path: str = Query(..., description="Project directory path"),
):
    """Get current smart orchestrator state if active."""
    for mode in ("feature", "greenfield", "refactor", "fix", "evolve"):
        key = f"native_{mode}_{path}"
        runner = _running_engines.get(key)
        if runner and hasattr(runner, "get_state"):
            return runner.get_state()
    return {"active": False, "workers": []}


@router.get("/api/swarm/mail")
async def get_swarm_mail(
    path: str = Query(..., description="Project directory path"),
    recipient: Optional[str] = Query(None, description="Filter by recipient"),
    msg_type: Optional[str] = Query(None, description="Filter by message type"),
    unread_only: bool = Query(False, description="Only return unread messages"),
    limit: int = Query(50, description="Max messages to return"),
):
    """Get inter-agent mail messages for a swarm."""
    try:
        from state.mail import MailStore
        store = MailStore(Path(path))
        if not store.db_path.exists():
            return {"messages": [], "stats": {}}
        store.initialize()
        messages = store.get_messages(
            recipient=recipient,
            msg_type=msg_type,
            unread_only=unread_only,
            limit=limit,
        )
        stats = store.get_stats()
        store.close()
        return {
            "messages": [m.to_dict() for m in messages],
            "stats": stats,
        }
    except Exception as e:
        return {"messages": [], "stats": {}, "error": str(e)}


@router.post("/api/swarm/mail/read")
async def mark_mail_read(
    path: str = Query(..., description="Project directory path"),
    message_id: str = Query("", description="Message ID to mark read (empty = mark all)"),
    recipient: str = Query("orchestrator", description="Recipient for mark-all"),
):
    """Mark swarm mail messages as read."""
    try:
        from state.mail import MailStore
        store = MailStore(Path(path))
        if not store.db_path.exists():
            return {"status": "no_mail_db"}
        store.initialize()
        if message_id:
            store.mark_read(message_id)
        else:
            store.mark_all_read(recipient)
        store.close()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/api/swarm/health")
async def get_swarm_health(
    path: str = Query(..., description="Project directory path"),
):
    """Get watchdog health status for swarm workers."""
    health_file = get_paths(Path(path)).swarm_dir / "watchdog_state.json"
    if health_file.exists():
        try:
            return json.loads(health_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"running": False, "workers": {}, "total_events": 0, "recent_events": []}


@router.get("/api/swarm/merge-queue")
async def get_merge_queue(
    path: str = Query(..., description="Project directory path"),
    status: Optional[str] = Query(None, description="Filter by status"),
):
    """Get merge queue entries and stats."""
    try:
        from core.merge_queue import MergeQueue
        queue = MergeQueue(Path(path))
        if not queue.db_path.exists():
            return {"entries": [], "stats": {"total": 0, "by_status": {}, "by_resolution_tier": {}}}
        queue.initialize()
        entries = queue.get_queue(status=status)
        stats = queue.get_stats()
        queue.close()
        return {
            "entries": [e.to_dict() for e in entries],
            "stats": stats,
        }
    except Exception as e:
        return {"entries": [], "stats": {}, "error": str(e)}


@router.get("/api/approval/pending")
async def get_approval_pending(
    path: str = Query(..., description="Project directory path"),
):
    """Get pending approval request if any."""
    pending_file = get_paths(Path(path)).resolve_read("approval_pending.json")
    if pending_file.exists():
        try:
            return json.loads(pending_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return None


@router.post("/api/approval/resolve")
async def resolve_approval(
    path: str = Query(..., description="Project directory path"),
    decision: str = Query(..., description="approved|rejected|reflect|skipped"),
    feedback: str = Query("", description="Optional feedback text"),
):
    """Resolve a pending approval request."""
    try:
        from features.approval import resolve_approval as _resolve
        _resolve(Path(path), decision, feedback)
        return {"status": "ok", "decision": decision}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/api/swarm/workers/{worker_id}/nudge")
async def nudge_worker(worker_id: str, req: NudgeRequest):
    """Send a nudge to a specific swarm worker."""
    try:
        from services.watchdog import SwarmWatchdog, WorkerHealth

        state_file = get_paths(Path(req.path)).swarm_state
        worker_pid = None
        worker_dir = req.path

        if state_file.exists():
            state = json.loads(state_file.read_text(encoding="utf-8"))
            for worker in state.get("workers", []):
                if str(worker.get("id")) == worker_id or worker.get("name") == worker_id:
                    worker_dir = worker.get("worktree_path") or worker.get("work_dir") or req.path
                    worker_pid = worker.get("pid")
                    break

        health = WorkerHealth(
            worker_id=int(worker_id) if worker_id.isdigit() else 0,
            pid=worker_pid,
            worktree_path=worker_dir,
        )

        wd = SwarmWatchdog()
        nudge_result = wd._nudge_worker(health, req.message)

        return {
            "status": "ok",
            "worker_id": worker_id,
            "method": nudge_result["method"],
            "success": nudge_result["success"],
        }
    except Exception as e:
        return {"status": "error", "message": str(e), "method": "none", "success": False}


@router.post("/api/swarm/workers/{worker_id}/terminate")
async def terminate_worker(worker_id: str, req: TerminateRequest):
    """Terminate a swarm worker process by killing its PID."""
    try:
        state_file = get_paths(Path(req.path)).swarm_state
        if not state_file.exists():
            return {"status": "error", "message": "No swarm state file found"}
        state = json.loads(state_file.read_text(encoding="utf-8"))
        for worker in state.get("workers", []):
            if worker.get("id") == worker_id or worker.get("name") == worker_id:
                pid = worker.get("pid")
                if not pid:
                    return {"status": "error", "message": f"No PID found for worker '{worker_id}'"}
                try:
                    os.kill(pid, signal.SIGTERM)
                    return {"status": "ok", "worker_id": worker_id, "pid": pid}
                except ProcessLookupError:
                    return {"status": "error", "message": f"Process {pid} not found (already exited)"}
                except PermissionError:
                    return {"status": "error", "message": f"Permission denied to kill process {pid}"}
        return {"status": "error", "message": f"Worker '{worker_id}' not found in swarm state"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
