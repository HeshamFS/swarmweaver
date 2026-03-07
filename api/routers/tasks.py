"""Task list, specs, security report, and project data endpoints."""

import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Query

from core.paths import get_paths

router = APIRouter()


@router.get("/api/tasks")
async def get_tasks(path: str = Query(..., description="Project directory path")):
    """Get task list for a project."""
    project_dir = Path(path)

    paths = get_paths(project_dir)
    task_file = paths.task_list
    if task_file.exists():
        try:
            data = json.loads(task_file.read_text(encoding="utf-8"))
            return data
        except (json.JSONDecodeError, OSError):
            return {"error": "Failed to read task list"}

    return {"metadata": {}, "tasks": []}


@router.get("/api/task-groups")
async def get_task_groups(
    path: str = Query(..., description="Project directory path"),
):
    """List task groups for a project."""
    try:
        from state.task_groups import TaskGroupStore
        store = TaskGroupStore(Path(path))
        groups = store.list_groups()
        return {"groups": [g.to_dict() for g in groups]}
    except Exception as e:
        return {"groups": [], "error": str(e)}


@router.get("/api/progress-notes")
async def get_progress_notes(
    path: str = Query(..., description="Project directory path"),
):
    """Get the claude-progress.txt handoff notes."""
    paths = get_paths(Path(path))
    notes_file = paths.resolve_read("claude-progress.txt")
    if notes_file.exists():
        return {"notes": notes_file.read_text(encoding="utf-8")}
    return {"notes": ""}


@router.get("/api/security-report")
async def get_security_report(
    path: str = Query(..., description="Project directory path"),
):
    """Read the security_report.json produced by the scan phase."""
    paths = get_paths(Path(path))
    report_path = paths.resolve_read("security_report.json")
    if not report_path.exists():
        return {"report": None}
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
        return {"report": data}
    except (json.JSONDecodeError, OSError):
        return {"report": None}


@router.post("/api/security-report/approve")
async def approve_security_report(
    path: str = Query(..., description="Project directory path"),
    body: dict = None,
):
    """Approve selected security findings and create task_list.json from them."""
    if not body:
        return {"status": "error", "message": "Missing request body"}

    approved_ids = set(body.get("approved_ids", []))
    ignored_reasons = body.get("ignored_reasons", {})

    paths = get_paths(Path(path))
    report_path = paths.resolve_read("security_report.json")
    if not report_path.exists():
        return {"status": "error", "message": "No security report found"}

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"status": "error", "message": "Failed to read security report"}

    findings = report.get("findings", [])

    severity_priority = {
        "critical": 1, "high": 2, "medium": 3, "low": 4, "info": 5,
    }

    tasks = []
    for f in findings:
        fid = f.get("id", "")
        if fid in approved_ids:
            tasks.append({
                "id": fid,
                "title": f"{f.get('severity', 'medium').upper()}: {f.get('title', '')}",
                "description": f.get("description", ""),
                "category": f.get("category", "security"),
                "status": "pending",
                "priority": severity_priority.get(f.get("severity", "medium"), 3),
                "acceptance_criteria": f.get("acceptance_criteria", []),
                "files_affected": [f["file"]] if f.get("file") else [],
                "notes": f.get("recommendation", ""),
            })

    tasks.sort(key=lambda t: t.get("priority", 3))

    task_list = {
        "metadata": {
            "mode": "security",
            "version": "1.0",
            "created_at": datetime.now().isoformat(),
            "total_findings": len(findings),
            "approved_findings": len(tasks),
            "ignored_findings": len(ignored_reasons),
        },
        "tasks": tasks,
    }

    paths.ensure_dir()
    paths.task_list.write_text(json.dumps(task_list, indent=2), encoding="utf-8")

    return {"status": "ok", "tasks_created": len(tasks)}


@router.get("/api/output-log")
async def get_output_log(
    path: str = Query(..., description="Project directory path"),
    lines: int = Query(200, description="Number of lines to return (from end)"),
):
    """Read the last N lines of agent_output.log for a project."""
    log_path = get_paths(Path(path)).resolve_read("agent_output.log")
    if not log_path.exists():
        return {"lines": []}
    try:
        all_lines = log_path.read_text(encoding="utf-8").splitlines()
        return {"lines": all_lines[-lines:]}
    except OSError:
        return {"lines": []}


@router.get("/api/activity-log")
async def get_activity_log(
    path: str = Query(..., description="Project directory path"),
    limit: int = Query(10000, description="Max events to return"),
):
    """Return persisted WebSocket activity events for a completed project.

    Used by the frontend to replay the full agent/orchestrator/worker history
    when reopening a project from Recent Projects.
    """
    import json as _json
    log_path = get_paths(Path(path)).activity_log
    if not log_path.exists():
        return {"events": []}
    events = []
    try:
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(_json.loads(line))
            except _json.JSONDecodeError:
                continue
    except OSError:
        return {"events": []}
    # Return tail if over limit so the most recent/interesting events are kept
    return {"events": events[-limit:]}


@router.get("/api/errors")
async def get_errors(
    path: str = Query(..., description="Project directory path"),
    limit: int = Query(200, description="Max errors to return"),
    agent: str = Query(None, description="Filter by agent: orchestrator or worker-N"),
):
    """Return persisted errors from orchestrator and workers.

    Each record includes agent, tool_name, tool_input, error, and timestamp.
    Used by the frontend Errors panel for debugging and on-the-fly fixes.
    """
    log_path = get_paths(Path(path)).error_log
    if not log_path.exists():
        return {"errors": [], "total": 0}
    errors = []
    try:
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if agent and rec.get("agent") != agent:
                    continue
                errors.append(rec)
            except json.JSONDecodeError:
                continue
    except OSError:
        return {"errors": [], "total": 0}
    # Most recent first
    errors.reverse()
    total = len(errors)
    return {"errors": errors[:limit], "total": total}


@router.get("/api/spec")
async def get_spec(
    path: str = Query(..., description="Project directory path"),
):
    """Read generated app_spec.txt from project directory."""
    spec_path = get_paths(Path(path)).resolve_read("app_spec.txt")
    if not spec_path.exists():
        return {"spec": None}
    return {"spec": spec_path.read_text(encoding="utf-8")}


@router.post("/api/spec")
async def save_spec(
    path: str = Query(..., description="Project directory path"),
    body: dict = None,
):
    """Save edited spec back to app_spec.txt."""
    if not body or "spec" not in body:
        return {"status": "error", "message": "Missing 'spec' in request body"}
    paths = get_paths(Path(path))
    paths.ensure_dir()
    paths.app_spec.write_text(body["spec"], encoding="utf-8")
    return {"status": "saved"}


@router.get("/api/reflections")
async def get_reflections(
    path: str = Query(..., description="Project directory path"),
):
    """Read session_reflections.json."""
    reflections_file = get_paths(Path(path)).resolve_read("session_reflections.json")
    if not reflections_file.exists():
        return {"reflections": []}
    try:
        data = json.loads(reflections_file.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return {"reflections": data}
        return data
    except (json.JSONDecodeError, OSError):
        return {"reflections": []}


@router.get("/api/codebase-profile")
async def get_codebase_profile(
    path: str = Query(..., description="Project directory path"),
):
    """Read codebase_profile.json."""
    profile_file = get_paths(Path(path)).resolve_read("codebase_profile.json")
    if not profile_file.exists():
        return {}
    try:
        return json.loads(profile_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


@router.get("/api/specs")
async def list_specs(
    path: str = Query(..., description="Project directory path"),
):
    """List all specs for a project."""
    try:
        from features.spec_workflow import SpecManager
        mgr = SpecManager(Path(path))
        return {"specs": mgr.list_specs()}
    except Exception as e:
        return {"specs": [], "error": str(e)}


@router.get("/api/specs/{task_id}")
async def read_spec(
    task_id: str,
    path: str = Query(..., description="Project directory path"),
):
    """Read a spec for a specific task."""
    try:
        from features.spec_workflow import SpecManager
        mgr = SpecManager(Path(path))
        content = mgr.read_spec(task_id)
        if content is None:
            return {"content": None, "found": False}
        return {"content": content, "found": True, "task_id": task_id}
    except Exception as e:
        return {"content": None, "found": False, "error": str(e)}


@router.post("/api/specs/{task_id}")
async def write_spec(
    task_id: str,
    path: str = Query(..., description="Project directory path"),
    content: str = Query(..., description="Spec content (markdown)"),
    author: str = Query("", description="Author name"),
):
    """Write a spec for a specific task."""
    try:
        from features.spec_workflow import SpecManager
        mgr = SpecManager(Path(path))
        spec_path = mgr.write_spec(task_id, content, author)
        return {"status": "ok", "path": str(spec_path), "task_id": task_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}
