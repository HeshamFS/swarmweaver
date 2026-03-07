"""Session history, runs, timeline, events, and ADR endpoints."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query

from core.paths import get_paths

router = APIRouter()


@router.get("/api/session-stats")
async def get_session_stats(
    path: str = Query(..., description="Project directory path"),
):
    """Get aggregate session statistics from audit log."""
    project_dir = Path(path)
    audit_path = get_paths(project_dir).resolve_read("audit.log")

    stats: dict = {
        "tool_call_count": 0,
        "tool_counts": {},
        "error_count": 0,
        "file_touches": {},
    }

    if audit_path.exists():
        try:
            for line in audit_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    tool = entry.get("tool_name", "unknown")
                    stats["tool_call_count"] += 1
                    stats["tool_counts"][tool] = stats["tool_counts"].get(tool, 0) + 1
                    if entry.get("is_error"):
                        stats["error_count"] += 1
                    tool_input = entry.get("tool_input", {})
                    if isinstance(tool_input, dict):
                        file_path = tool_input.get("file_path") or tool_input.get("path", "")
                        if file_path and tool in ("Write", "Edit", "Read"):
                            stats["file_touches"][file_path] = stats["file_touches"].get(file_path, 0) + 1
                except json.JSONDecodeError:
                    continue
        except OSError:
            pass

    return stats


@router.get("/api/session-history")
async def get_session_history(
    path: str = Query(..., description="Project directory path"),
    limit: int = Query(50, description="Max commits to return"),
):
    """Get git commit timeline with task state snapshots."""
    from services.replay import SessionReplayManager
    mgr = SessionReplayManager(Path(path))
    return {"timeline": mgr.get_full_timeline(limit)}


@router.get("/api/replay/commit/{sha}")
async def get_replay_commit(
    sha: str,
    path: str = Query(..., description="Project directory path"),
):
    """Get task state and diff at a specific commit."""
    from services.replay import SessionReplayManager
    mgr = SessionReplayManager(Path(path))
    task_state = mgr.get_task_state_at_commit(sha)
    diff = mgr.get_diff_at_commit(sha)
    return {
        "sha": sha,
        "task_state": task_state,
        "diff": diff,
    }


@router.get("/api/audit-timeline")
async def get_audit_timeline(
    path: str = Query(..., description="Project directory path"),
):
    """Get audit log entries for replay."""
    from services.replay import SessionReplayManager
    mgr = SessionReplayManager(Path(path))
    return {"entries": mgr.get_audit_timeline()}


@router.get("/api/runs")
async def get_runs(
    path: str = Query(..., description="Project directory path"),
    status: Optional[str] = Query(None),
    limit: int = Query(20),
):
    """List recent runs."""
    try:
        from state.runs import RunStore
        store = RunStore(Path(path))
        if not store.db_path.exists():
            return {"runs": []}
        store.initialize()
        runs = store.list_runs(limit=limit, status=status)
        store.close()
        return {"runs": [r.to_dict() for r in runs]}
    except Exception as e:
        return {"runs": [], "error": str(e)}


@router.get("/api/runs/active")
async def get_active_run(
    path: str = Query(..., description="Project directory path"),
):
    """Get the currently active run."""
    try:
        from state.runs import RunStore
        store = RunStore(Path(path))
        if not store.db_path.exists():
            return {"run": None}
        store.initialize()
        run = store.get_active_run()
        store.close()
        return {"run": run.to_dict() if run else None}
    except Exception as e:
        return {"run": None, "error": str(e)}


@router.get("/api/runs/compare")
async def compare_runs(
    path: str = Query(..., description="Project directory path"),
    run1: str = Query(..., description="First run ID or timestamp"),
    run2: str = Query(..., description="Second run ID or timestamp"),
):
    """Compare two runs by their output logs and budget state snapshots."""
    try:
        project_dir = Path(path)

        def _load_run_data(run_id: str) -> dict:
            _proj_paths = get_paths(project_dir)
            run_dir = _proj_paths.runs_dir / run_id
            data: dict = {"run_id": run_id, "tasks_completed": 0, "tasks_total": 0,
                          "cost_usd": 0.0, "duration_seconds": 0, "errors": 0, "tool_calls": 0}

            state_file = run_dir / "budget_state.json"
            if not state_file.exists():
                state_file = _proj_paths.resolve_read("budget_state.json")

            if state_file.exists():
                try:
                    budget = json.loads(state_file.read_text(encoding="utf-8"))
                    data["cost_usd"] = budget.get("estimated_cost_usd", 0)
                    data["total_input_tokens"] = budget.get("total_input_tokens", 0)
                    data["total_output_tokens"] = budget.get("total_output_tokens", 0)
                    data["session_count"] = budget.get("session_count", 0)
                    if budget.get("start_time") and budget.get("end_time"):
                        from datetime import datetime as _dt
                        try:
                            start = _dt.fromisoformat(budget["start_time"])
                            end = _dt.fromisoformat(budget["end_time"])
                            data["duration_seconds"] = (end - start).total_seconds()
                        except (ValueError, TypeError):
                            pass
                except (json.JSONDecodeError, OSError):
                    pass

            task_file = run_dir / "task_list.json"
            if not task_file.exists():
                task_file = _proj_paths.resolve_read("task_list.json")
            if task_file.exists():
                try:
                    tl = json.loads(task_file.read_text(encoding="utf-8"))
                    tasks = tl.get("tasks", [])
                    data["tasks_total"] = len(tasks)
                    data["tasks_completed"] = len([t for t in tasks if t.get("status") == "done"])
                except (json.JSONDecodeError, OSError):
                    pass

            audit_file = run_dir / "audit.log"
            if not audit_file.exists():
                audit_file = _proj_paths.resolve_read("audit.log")
            if audit_file.exists():
                try:
                    for line in audit_file.read_text(encoding="utf-8", errors="replace").splitlines():
                        try:
                            entry = json.loads(line)
                            data["tool_calls"] = data.get("tool_calls", 0) + 1
                            if entry.get("is_error"):
                                data["errors"] = data.get("errors", 0) + 1
                        except (json.JSONDecodeError, TypeError):
                            pass
                except OSError:
                    pass

            return data

        run1_data = _load_run_data(run1)
        run2_data = _load_run_data(run2)

        comparison = {
            "run1": run1_data,
            "run2": run2_data,
            "deltas": {
                "cost_usd": round(run2_data["cost_usd"] - run1_data["cost_usd"], 4),
                "duration_seconds": run2_data["duration_seconds"] - run1_data["duration_seconds"],
                "tasks_completed": run2_data["tasks_completed"] - run1_data["tasks_completed"],
                "errors": run2_data["errors"] - run1_data["errors"],
                "tool_calls": run2_data.get("tool_calls", 0) - run1_data.get("tool_calls", 0),
            },
        }
        return comparison

    except Exception as e:
        return {"error": str(e), "run1": {}, "run2": {}, "deltas": {}}


@router.get("/api/events")
async def get_events(
    path: str = Query(..., description="Project directory path"),
    agent_name: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    since: Optional[str] = Query(None),
    limit: int = Query(200),
):
    """Query the persistent event store."""
    try:
        from state.events import EventStore
        store = EventStore(Path(path))
        if not store.db_path.exists():
            return {"events": [], "stats": {}}
        store.initialize()
        events = store.query(agent_name=agent_name, event_type=event_type, level=level, since=since, limit=limit)
        stats = store.get_stats()
        store.close()
        return {"events": [e.to_dict() for e in events], "stats": stats}
    except Exception as e:
        return {"events": [], "stats": {}, "error": str(e)}


@router.get("/api/events/tool-stats")
async def get_tool_stats(
    path: str = Query(..., description="Project directory path"),
):
    """Get tool usage statistics from the event store."""
    try:
        from state.events import EventStore
        store = EventStore(Path(path))
        if not store.db_path.exists():
            return {"tool_stats": []}
        store.initialize()
        stats = store.tool_statistics()
        store.close()
        return {"tool_stats": stats}
    except Exception as e:
        return {"tool_stats": [], "error": str(e)}


@router.get("/api/timeline")
async def get_timeline(
    path: str = Query(..., description="Project directory path"),
    since: Optional[str] = Query(None, description="ISO timestamp filter"),
    limit: int = Query(200, description="Max events to return"),
    agent: Optional[str] = Query(None, description="Filter by agent name"),
):
    """Get cross-agent timeline merging events, mail, and audit logs."""
    try:
        from services.timeline import CrossAgentTimeline
        tl = CrossAgentTimeline()
        events = tl.get_timeline(Path(path), since=since, limit=limit, agent_filter=agent)
        stats = tl.get_timeline_stats(Path(path))
        return {"events": events, "stats": stats}
    except Exception as e:
        return {"events": [], "stats": {}, "error": str(e)}


@router.get("/api/adrs")
async def list_adrs(
    path: str = Query(..., description="Project directory path"),
):
    """List Architecture Decision Records for a project."""
    from services.adr import ADRManager
    mgr = ADRManager(Path(path))
    return {"adrs": mgr.list_adrs()}


@router.get("/api/adrs/{filename}")
async def read_adr(
    filename: str,
    path: str = Query(..., description="Project directory path"),
):
    """Read the full content of an ADR file."""
    from services.adr import ADRManager
    mgr = ADRManager(Path(path))
    content = mgr.read_adr(filename)
    if content is None:
        return {"error": f"ADR '{filename}' not found"}
    return {"filename": filename, "content": content}


@router.get("/api/session/chain")
async def get_session_chain(path: str = Query(..., description="Project directory path")):
    """Get all sessions in the current chain."""
    try:
        from state.session_checkpoint import ChainManager
        project_dir = Path(path)
        cm = ChainManager(project_dir)
        chain_id = cm.get_active_chain_id()
        if not chain_id:
            return []
        entries = cm.get_chain(chain_id)
        return entries
    except Exception as e:
        return {"error": str(e)}
